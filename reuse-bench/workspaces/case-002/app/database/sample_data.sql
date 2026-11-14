-- ============================================================================
-- Data Assistant — Sample PostgreSQL Database
-- ============================================================================
-- This script creates a small analytics dataset for demonstration purposes.
-- Tables: customers, products, orders, sales
-- ============================================================================

-- Drop tables if they exist (for clean re-initialization)
DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- ============================================================================
-- CUSTOMERS
-- ============================================================================
CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    first_name    VARCHAR(50) NOT NULL,
    last_name     VARCHAR(50) NOT NULL,
    email         VARCHAR(100) UNIQUE NOT NULL,
    city          VARCHAR(50),
    state         VARCHAR(50),
    country       VARCHAR(50) DEFAULT 'USA',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO customers (first_name, last_name, email, city, state, country) VALUES
('Alice',   'Johnson',  'alice.johnson@example.com',   'New York',      'NY', 'USA'),
('Bob',     'Smith',    'bob.smith@example.com',       'San Francisco', 'CA', 'USA'),
('Charlie', 'Williams', 'charlie.w@example.com',       'Chicago',       'IL', 'USA'),
('Diana',   'Brown',    'diana.brown@example.com',     'Austin',        'TX', 'USA'),
('Eve',     'Davis',    'eve.davis@example.com',       'Seattle',       'WA', 'USA'),
('Frank',   'Garcia',   'frank.garcia@example.com',    'Miami',         'FL', 'USA'),
('Grace',   'Martinez', 'grace.martinez@example.com',  'Denver',        'CO', 'USA'),
('Henry',   'Wilson',   'henry.wilson@example.com',    'Boston',        'MA', 'USA'),
('Ivy',     'Moore',    'ivy.moore@example.com',       'Portland',      'OR', 'USA'),
('Jack',    'Taylor',   'jack.taylor@example.com',     'Atlanta',       'GA', 'USA'),
('Karen',   'Anderson', 'karen.anderson@example.com',  'Phoenix',       'AZ', 'USA'),
('Leo',     'Thomas',   'leo.thomas@example.com',      'Las Vegas',     'NV', 'USA');

-- ============================================================================
-- PRODUCTS
-- ============================================================================
CREATE TABLE products (
    product_id    SERIAL PRIMARY KEY,
    product_name  VARCHAR(100) NOT NULL,
    category      VARCHAR(50) NOT NULL,
    price         DECIMAL(10, 2) NOT NULL,
    stock_qty     INTEGER DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO products (product_name, category, price, stock_qty) VALUES
('Laptop Pro 15',       'Electronics', 1299.99, 150),
('Wireless Mouse',      'Electronics',   29.99, 500),
('Mechanical Keyboard', 'Electronics',   89.99, 300),
('USB-C Hub',           'Electronics',   49.99, 200),
('Monitor 27"',         'Electronics',  399.99, 100),
('Standing Desk',       'Furniture',    599.99,  75),
('Ergonomic Chair',     'Furniture',    449.99,  60),
('Desk Lamp LED',       'Furniture',     39.99, 400),
('Notebook Pack',       'Stationery',    12.99, 800),
('Premium Pen Set',     'Stationery',    24.99, 350),
('Webcam HD',           'Electronics',   79.99, 180),
('Noise-Cancel Headphones', 'Electronics', 199.99, 120);

-- ============================================================================
-- ORDERS
-- ============================================================================
CREATE TABLE orders (
    order_id      SERIAL PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date    DATE NOT NULL,
    status        VARCHAR(20) DEFAULT 'completed',
    total_amount  DECIMAL(10, 2),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO orders (customer_id, order_date, status, total_amount) VALUES
(1,  '2025-01-15', 'completed',  1349.98),
(2,  '2025-01-20', 'completed',   119.98),
(3,  '2025-02-05', 'completed',   499.98),
(1,  '2025-02-14', 'completed',    89.99),
(4,  '2025-03-01', 'completed',  1749.98),
(5,  '2025-03-10', 'shipped',     629.98),
(6,  '2025-03-15', 'completed',    79.99),
(2,  '2025-04-01', 'completed',   449.99),
(7,  '2025-04-12', 'completed',   199.99),
(8,  '2025-04-20', 'shipped',     139.98),
(3,  '2025-05-01', 'completed',  1299.99),
(9,  '2025-05-05', 'pending',      37.98),
(10, '2025-05-10', 'completed',   399.99),
(4,  '2025-05-15', 'completed',    89.99),
(11, '2025-05-20', 'completed',   649.98);

-- ============================================================================
-- SALES (denormalized fact table for analytics)
-- ============================================================================
CREATE TABLE sales (
    sale_id       SERIAL PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    quantity      INTEGER NOT NULL,
    unit_price    DECIMAL(10, 2) NOT NULL,
    total_price   DECIMAL(10, 2) NOT NULL,
    sale_date     DATE NOT NULL,
    region        VARCHAR(20)
);

INSERT INTO sales (order_id, product_id, customer_id, quantity, unit_price, total_price, sale_date, region) VALUES
(1,  1,  1,  1, 1299.99, 1299.99, '2025-01-15', 'East'),
(1,  2,  1,  1,   29.99,   29.99, '2025-01-15', 'East'),
(2,  3,  2,  1,   89.99,   89.99, '2025-01-20', 'West'),
(2,  2,  2,  1,   29.99,   29.99, '2025-01-20', 'West'),
(3,  5,  3,  1,  399.99,  399.99, '2025-02-05', 'Central'),
(3,  4,  3,  2,   49.99,   99.98, '2025-02-05', 'Central'),
(4,  3,  1,  1,   89.99,   89.99, '2025-02-14', 'East'),
(5,  1,  4,  1, 1299.99, 1299.99, '2025-03-01', 'South'),
(5,  7,  4,  1,  449.99,  449.99, '2025-03-01', 'South'),
(6,  6,  5,  1,  599.99,  599.99, '2025-03-10', 'West'),
(6,  2,  5,  1,   29.99,   29.99, '2025-03-10', 'West'),
(7,  11, 6,  1,   79.99,   79.99, '2025-03-15', 'South'),
(8,  7,  2,  1,  449.99,  449.99, '2025-04-01', 'West'),
(9,  12, 7,  1,  199.99,  199.99, '2025-04-12', 'West'),
(10, 3,  8,  1,   89.99,   89.99, '2025-04-20', 'East'),
(10, 4,  8,  1,   49.99,   49.99, '2025-04-20', 'East'),
(11, 1,  3,  1, 1299.99, 1299.99, '2025-05-01', 'Central'),
(12, 9,  9,  2,   12.99,   25.98, '2025-05-05', 'West'),
(12, 10, 9,  1,   24.99,   24.99, '2025-05-05', 'West'),  -- Adjusted: was 12.00
(13, 5, 10,  1,  399.99,  399.99, '2025-05-10', 'South'),
(14, 3,  4,  1,   89.99,   89.99, '2025-05-15', 'South'),
(15, 6, 11,  1,  599.99,  599.99, '2025-05-20', 'West'),
(15, 4, 11,  1,   49.99,   49.99, '2025-05-20', 'West');
