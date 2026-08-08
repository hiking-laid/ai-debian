-- ============================================================================
-- toddler_dinner — database schema (Postgres)
--
-- GENERATED FILE — do not edit by hand. Generated from the Alembic migrations.
-- Regenerate with:
--     alembic upgrade head --sql > db/schema.sql
--
-- Two ways to initialize a database (e.g. your NAS Postgres):
--   1. Recommended:  toddler-dinner db upgrade        (applies Alembic migrations)
--   2. Direct psql:  psql "$DSN" -f db/schema.sql      (no Python needed)
-- ============================================================================

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> b470597e21b7

CREATE TABLE menus (
    id SERIAL NOT NULL, 
    for_date DATE NOT NULL, 
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    notes TEXT, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_menus_for_date ON menus (for_date);

CREATE TABLE recipes (
    id SERIAL NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    min_age_months INTEGER NOT NULL, 
    texture VARCHAR(120), 
    source VARCHAR(20) NOT NULL, 
    approved BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_recipes_approved ON recipes (approved);

CREATE INDEX ix_recipes_title ON recipes (title);

CREATE TABLE dinner_history (
    id SERIAL NOT NULL, 
    recipe_id INTEGER, 
    title VARCHAR(200) NOT NULL, 
    served_on DATE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE SET NULL
);

CREATE INDEX ix_dinner_history_recipe_id ON dinner_history (recipe_id);

CREATE INDEX ix_dinner_history_served_on ON dinner_history (served_on);

CREATE TABLE ingredients (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    quantity FLOAT NOT NULL, 
    unit VARCHAR(40) NOT NULL, 
    position INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_ingredients_recipe_id ON ingredients (recipe_id);

CREATE TABLE menu_items (
    id SERIAL NOT NULL, 
    menu_id INTEGER NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    servings FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(menu_id) REFERENCES menus (id) ON DELETE CASCADE, 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id)
);

CREATE INDEX ix_menu_items_menu_id ON menu_items (menu_id);

CREATE INDEX ix_menu_items_recipe_id ON menu_items (recipe_id);

CREATE TABLE recipe_food_groups (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    food_group VARCHAR(30) NOT NULL, 
    servings FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_recipe_food_groups_recipe_id ON recipe_food_groups (recipe_id);

CREATE TABLE recipe_hazards (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    flag VARCHAR(60) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_recipe_hazards_recipe_id ON recipe_hazards (recipe_id);

CREATE TABLE recipe_nutrition (
    recipe_id INTEGER NOT NULL, 
    energy_kcal FLOAT, 
    protein_g FLOAT, 
    fat_g FLOAT, 
    carbs_g FLOAT, 
    fibre_g FLOAT, 
    iron_mg FLOAT, 
    calcium_mg FLOAT, 
    sodium_mg FLOAT, 
    PRIMARY KEY (recipe_id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE TABLE recipe_steps (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    position INTEGER NOT NULL, 
    text TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_recipe_steps_recipe_id ON recipe_steps (recipe_id);

CREATE TABLE recipe_tags (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    tag VARCHAR(60) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_recipe_tags_recipe_id ON recipe_tags (recipe_id);

CREATE TABLE shopping_lists (
    id SERIAL NOT NULL, 
    menu_id INTEGER, 
    budget FLOAT, 
    estimated_total FLOAT, 
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(menu_id) REFERENCES menus (id) ON DELETE SET NULL
);

CREATE INDEX ix_shopping_lists_menu_id ON shopping_lists (menu_id);

CREATE TABLE shopping_items (
    id SERIAL NOT NULL, 
    shopping_list_id INTEGER NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    quantity FLOAT NOT NULL, 
    unit VARCHAR(40) NOT NULL, 
    est_unit_cost FLOAT, 
    est_total_cost FLOAT, 
    store VARCHAR(60), 
    on_special BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(shopping_list_id) REFERENCES shopping_lists (id) ON DELETE CASCADE
);

CREATE INDEX ix_shopping_items_shopping_list_id ON shopping_items (shopping_list_id);

INSERT INTO alembic_version (version_num) VALUES ('b470597e21b7') RETURNING alembic_version.version_num;

-- Running upgrade b470597e21b7 -> 32316ea85c11

ALTER TABLE recipes ADD COLUMN cooked BOOLEAN DEFAULT false NOT NULL;

CREATE INDEX ix_recipes_cooked ON recipes (cooked);

UPDATE alembic_version SET version_num='32316ea85c11' WHERE alembic_version.version_num = 'b470597e21b7';

COMMIT;

