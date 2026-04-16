# Supabase 數據庫設計

## 概述
Mobile Hermes V2 使用 Supabase 作為主要數據庫。

## 表結構

### users 表
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE,
    name TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### conversations 表
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### messages 表
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id),
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### memory 表
```sql
CREATE TABLE memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    memory_type TEXT,
    content JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 索引優化
- messages(conversation_id, created_at)
- memory(user_id, memory_type)

[Metadata]: {"category": "integration", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
