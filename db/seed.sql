-- Synthetic marketplace seed data.
--
-- Schema is defined once, in shared/db_models.py (SQLAlchemy); this file carries only
-- data, so the two never drift out of sync. Loaded automatically the first time the
-- database is opened, or explicitly via `python db/seed_database.py --force`.
--
-- ALL DATA IS SYNTHETIC. No real products, sellers, customers, or transactions.
-- Product facts (SKU, category, supplier, storage bin) intentionally match
-- rag/data/catalog/electronics_catalog.md so the SQL store and the RAG corpus agree.

INSERT INTO products
    (product_id, name, sku, category, supplier, storage_location, price, competitor_price)
VALUES
    ('iphone-15',          'iPhone 15',          'IPH-15-BASE', 'Smartphones',        'Apple Inc.',          'Bin 4A, High-Security Zone',   999.00,  989.00),
    ('generic-headphones', 'Generic Headphones', 'GEN-HD-01',   'Audio Accessories',  'AudioTech Shenzen',   'Bin 12C, Standard Zone',        49.99,   NULL),
    ('premium-tv',         'Premium TV',         'P-TV-65',     'Home Entertainment', 'Samsung Electronics', 'Pallet Rack 2, Oversize Zone', 1200.00, 1080.00);

-- Stock levels chosen against warehouse_policy.md so the policy has something to bite on:
-- premium-tv at 3 units is below the "fewer than 5 units" low-stock line, and its 20% of
-- 30-day average (15 * 0.2 = 3) also puts it exactly on the restock trigger.
INSERT INTO inventory (product_id, stock_qty, avg_30d_sales, warehouse_zone)
VALUES
    ('iphone-15',          42,  120, 'High-Security Zone'),
    ('generic-headphones', 105,  50, 'Standard Zone'),
    ('premium-tv',           3,  15, 'Oversize Zone');

-- Sellers span both sides of every fraud_policy.md threshold, so risk queries have real
-- discrimination to do rather than a single obvious offender:
--   techworld-99  - 22% returns (over the 15% line) AND 4 complaints (over the 3/week line)
--   budget-bazaar - 18% returns (over the line) but only 1 complaint (under it)
--   pixelpoint    - 9% returns (under) but 5 complaints (over) - fails on the other axis
--   audioking     - clean on both counts
INSERT INTO sellers (seller_id, name, return_rate_pct, complaints_last_week, status, joined_date)
VALUES
    ('techworld-99',  'TechWorld 99',  22.0, 4, 'under_review', '2024-03-11'),
    ('audioking',     'AudioKing',      5.0, 0, 'active',       '2023-07-02'),
    ('budget-bazaar', 'Budget Bazaar', 18.0, 1, 'active',       '2025-01-19'),
    ('pixelpoint',    'PixelPoint',     9.0, 5, 'active',       '2024-11-30');

INSERT INTO orders (order_id, product_id, seller_id, status, order_date)
VALUES
    ('ORD-1001', 'iphone-15',          'techworld-99',  'delivered',   '2026-07-14'),
    ('ORD-1002', 'premium-tv',         'audioking',     'in_transit',  '2026-08-02'),
    ('ORD-1003', 'generic-headphones', 'budget-bazaar', 'returned',    '2026-07-28'),
    ('ORD-1004', 'iphone-15',          'pixelpoint',    'lost',        '2026-08-09'),
    ('ORD-1005', 'premium-tv',         'techworld-99',  'delivered',   '2026-08-15');
