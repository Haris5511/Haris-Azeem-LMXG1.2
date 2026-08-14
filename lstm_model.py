import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from collections import Counter
import re
import copy

# ==========================================
# 1. RAW TEXT (Data Loading)
# ==========================================
df = pd.read_csv('news_final_v2.csv').dropna(subset=['Title', 'Category'])

label_encoder = LabelEncoder()
df['label'] = label_encoder.fit_transform(df['Category'])
num_classes = len(label_encoder.classes_)

# ==========================================
# 2. TOKENS (Tokenization & Vocabulary)
# ==========================================
def clean_and_tokenize(text):
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[^\w\s]', '', text.lower())
    return text.split()

words = [word for text in df['Title'] for word in clean_and_tokenize(text)]
vocab_counts = Counter(words)

# Sirf un words ko rakhein jo kam az kam 2 baar aaye hain
vocab = {word: i + 2 for i, (word, count) in enumerate(vocab_counts.items()) if count > 1}
vocab['<PAD>'] = 0
vocab['<UNK>'] = 1

def text_to_sequence(text, max_len=40):
    tokens = clean_and_tokenize(text)
    seq = [vocab.get(token, vocab['<UNK>']) for token in tokens]
    if len(seq) < max_len:
        seq = seq + [vocab['<PAD>']] * (max_len - len(seq))
    else:
        seq = seq[:max_len]
    return seq

df['sequence'] = df['Title'].apply(text_to_sequence)
X = np.array(df['sequence'].tolist())
y = df['label'].values

X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

class NewsDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.tensor(X, dtype=torch.long)
        self.y = torch.tensor(y, dtype=torch.long)
    def __len__(self): return len(self.X)
    def __getitem__(self, idx): return self.X[idx], self.y[idx]

train_loader = DataLoader(NewsDataset(X_train, y_train), batch_size=32, shuffle=True)
val_loader = DataLoader(NewsDataset(X_val, y_val), batch_size=32, shuffle=False)

# ==========================================
# 3. PIPELINE MODEL (Embeddings -> Hidden -> Features -> Classifier)
# ==========================================
class PipelineLSTM(nn.Module):
    def __init__(self, vocab_size, embed_dim=256, hidden_dim=128, num_classes=6):
        super(PipelineLSTM, self).__init__()
        
        # Block 3: Embeddings
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        
        # Block 4: Hidden layers (Bidirectional LSTM)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, num_layers=2, 
                            batch_first=True, bidirectional=True, dropout=0.4)
        
        # Block 6: Classifier
        # Input size hidden_dim * 4 hoga kyunke hum Bidirectional ki Max aur Mean pooling combine kar rahe hain
        self.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(hidden_dim * 4, 128),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(128, num_classes)
        )
        
    def forward(self, x):
        # Embeddings
        embedded = self.embedding(x)
        
        # Hidden layers
        lstm_out, _ = self.lstm(embedded)
        
        # Block 5: Learned features (Advanced Pooling)
        # Sentence ke har hissay se important features nikalna
        avg_pool = torch.mean(lstm_out, dim=1)
        max_pool, _ = torch.max(lstm_out, dim=1)
        learned_features = torch.cat((avg_pool, max_pool), dim=1)
        
        # Classifier & Block 7: Prediction
        prediction = self.classifier(learned_features)
        return prediction

# Model Initialization
vocab_size = max(vocab.values()) + 1
model = PipelineLSTM(vocab_size=vocab_size, embed_dim=256, hidden_dim=128, num_classes=num_classes)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)

criterion = nn.CrossEntropyLoss()
# Learning rate thora kam kiya hai taake stable training ho, aur weight decay lagaya hai
optimizer = optim.Adam(model.parameters(), lr=0.0005, weight_decay=1e-4)

# ==========================================
# TRAINING SCRIPT
# ==========================================
print("Training Pipeline Model...\n")
epochs = 20
best_val_acc = 0
patience = 4
patience_counter = 0
best_model_weights = copy.deepcopy(model.state_dict())

for epoch in range(epochs):
    model.train()
    total_train_loss, correct_train, total_train = 0, 0, 0
    for batch_x, batch_y in train_loader:
        batch_x, batch_y = batch_x.to(device), batch_y.to(device)
        optimizer.zero_grad()
        output = model(batch_x)
        loss = criterion(output, batch_y)
        loss.backward()
        optimizer.step()
        
        total_train_loss += loss.item()
        _, predicted = torch.max(output.data, 1)
        total_train += batch_y.size(0)
        correct_train += (predicted == batch_y).sum().item()
    
    train_acc = 100 * correct_train / total_train
    
    model.eval()
    total_val_loss, correct_val, total_val = 0, 0, 0
    with torch.no_grad():
        for batch_x, batch_y in val_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            output = model(batch_x)
            loss = criterion(output, batch_y)
            total_val_loss += loss.item()
            _, predicted = torch.max(output, 1)
            total_val += batch_y.size(0)
            correct_val += (predicted == batch_y).sum().item()
            
    val_acc = 100 * correct_val / total_val
    print(f"Epoch {epoch+1:02d} | Train Acc: {train_acc:.2f}% | Val Acc: {val_acc:.2f}%")
    
    if val_acc > best_val_acc:
        best_val_acc = val_acc
        best_model_weights = copy.deepcopy(model.state_dict())
        patience_counter = 0
    else:
        patience_counter += 1
        if patience_counter >= patience:
            print("\nEarly stopping triggered!")
            break

model.load_state_dict(best_model_weights)
print(f"\nFinal Best Pipeline Accuracy: {best_val_acc:.2f}%")