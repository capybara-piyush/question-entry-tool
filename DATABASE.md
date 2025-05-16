# Database Schema Documentation


### Categories
Defines the various quiz categories (cooking, sports, etc.).

```sql
CREATE TABLE categories (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    description TEXT
);
```

### ProductTypes
Defines the types of product questions (oneplus, amazon, etc.).

```sql
CREATE TABLE product_types (
    product_type_id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

### Questions
Stores all quiz questions across categories.

```sql
CREATE TABLE questions (
    question_id SERIAL PRIMARY KEY,
    category_id INTEGER REFERENCES categories(category_id),
    question_text TEXT NOT NULL,
    time_limit INTEGER DEFAULT 13, -- seconds
    is_product_question BOOLEAN DEFAULT FALSE,
    product_type_id INTEGER REFERENCES product_types(product_type_id) NULL,
    hint TEXT NULL
);
```

### Options
Contains answer options for each question.

```sql
CREATE TABLE options (
    option_id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(question_id),
    option_text TEXT NOT NULL,
    is_correct BOOLEAN DEFAULT FALSE
);
```
