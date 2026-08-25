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

-- Running upgrade 32316ea85c11 -> c1d2e3f4a5b6

DELETE FROM dinner_history WHERE recipe_id IS NULL;

DELETE FROM dinner_history a
        USING dinner_history b
        WHERE a.recipe_id = b.recipe_id
          AND a.served_on = b.served_on
          AND a.id > b.id;

ALTER TABLE dinner_history DROP CONSTRAINT dinner_history_pkey;

ALTER TABLE dinner_history DROP COLUMN id;

ALTER TABLE dinner_history ALTER COLUMN recipe_id SET NOT NULL;

DROP INDEX ix_dinner_history_recipe_id;

ALTER TABLE dinner_history ADD CONSTRAINT dinner_history_pkey PRIMARY KEY (recipe_id, served_on);

ALTER TABLE dinner_history DROP CONSTRAINT dinner_history_recipe_id_fkey;

ALTER TABLE dinner_history ADD CONSTRAINT dinner_history_recipe_id_fkey FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE;

UPDATE alembic_version SET version_num='c1d2e3f4a5b6' WHERE alembic_version.version_num = '32316ea85c11';

-- Running upgrade c1d2e3f4a5b6 -> d4e5f6a7b8c9

CREATE TABLE recipe_equipment (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    position INTEGER DEFAULT '0' NOT NULL, 
    text TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_recipe_equipment_recipe_id ON recipe_equipment (recipe_id);

CREATE TABLE recipe_tips (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    position INTEGER DEFAULT '0' NOT NULL, 
    text TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE INDEX ix_recipe_tips_recipe_id ON recipe_tips (recipe_id);

UPDATE alembic_version SET version_num='d4e5f6a7b8c9' WHERE alembic_version.version_num = 'c1d2e3f4a5b6';

-- Running upgrade d4e5f6a7b8c9 -> e5f6a7b8c9d0

CREATE TABLE recipe_stickers (
    id SERIAL NOT NULL, 
    recipe_id INTEGER NOT NULL, 
    content TEXT NOT NULL, 
    target_section VARCHAR(30), 
    target_step_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE, 
    FOREIGN KEY(target_step_id) REFERENCES recipe_steps (id) ON DELETE SET NULL
);

CREATE INDEX ix_recipe_stickers_recipe_id ON recipe_stickers (recipe_id);

UPDATE alembic_version SET version_num='e5f6a7b8c9d0' WHERE alembic_version.version_num = 'd4e5f6a7b8c9';

-- Running upgrade e5f6a7b8c9d0 -> e158a335e2f2

CREATE TABLE inventory_items (
    id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    status VARCHAR(10) NOT NULL, 
    quantity FLOAT, 
    unit VARCHAR(40), 
    best_before DATE, 
    category VARCHAR(30), 
    opened BOOLEAN NOT NULL, 
    location VARCHAR(20) NOT NULL, 
    PRIMARY KEY (id)
);

COMMENT ON TABLE inventory_items IS 'Household catalog of stocked foods; matching keys off the unique name, not amounts. Seeded (all ''none'') on initial deployment; a future UI edits it.';

COMMENT ON COLUMN inventory_items.id IS 'Surrogate primary key.';

COMMENT ON COLUMN inventory_items.name IS 'Food name; unique catalog key (case-insensitive dedup in the repo).';

COMMENT ON COLUMN inventory_items.status IS 'Coarse stock status: have | low | none.';

COMMENT ON COLUMN inventory_items.quantity IS 'Optional amount; unused by matching/groceries.';

COMMENT ON COLUMN inventory_items.unit IS 'Optional unit; unused by matching/groceries.';

COMMENT ON COLUMN inventory_items.best_before IS 'Optional best-before date; display-only.';

COMMENT ON COLUMN inventory_items.category IS 'Food category, e.g. protein / vegetable.';

COMMENT ON COLUMN inventory_items.opened IS 'Whether the item is opened (carried, unused).';

COMMENT ON COLUMN inventory_items.location IS 'Storage location: fridge | shelf | freezer.';

CREATE UNIQUE INDEX ix_inventory_items_name ON inventory_items (name);

COMMENT ON COLUMN dinner_history.recipe_id IS 'Served recipe (PK part + FK, cascade delete).';

COMMENT ON COLUMN dinner_history.served_on IS 'Date served (PK part; household timezone).';

COMMENT ON COLUMN dinner_history.title IS 'Recipe title snapshot at serve time.';

COMMENT ON TABLE dinner_history IS 'What was served and when; drives variety exclusion + the history view. (recipe_id, served_on) is the primary key, so re-recording a dinner the same day is an idempotent upsert, not a duplicate.';

COMMENT ON COLUMN ingredients.id IS 'Surrogate primary key.';

COMMENT ON COLUMN ingredients.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN ingredients.name IS 'Ingredient name.';

COMMENT ON COLUMN ingredients.quantity IS 'Amount to use.';

COMMENT ON COLUMN ingredients.unit IS 'Unit for the amount, e.g. g / each / cup.';

COMMENT ON COLUMN ingredients.position IS 'Display order within the recipe.';

COMMENT ON TABLE ingredients IS 'Recipe ingredients with quantity + unit, ordered by position.';

COMMENT ON COLUMN menu_items.id IS 'Surrogate primary key.';

COMMENT ON COLUMN menu_items.menu_id IS 'Owning menu (FK, cascade delete).';

COMMENT ON COLUMN menu_items.recipe_id IS 'Referenced recipe (FK).';

COMMENT ON COLUMN menu_items.servings IS 'Number of servings.';

COMMENT ON TABLE menu_items IS 'Recipes placed on a menu, with servings.';

COMMENT ON COLUMN menus.id IS 'Surrogate primary key.';

COMMENT ON COLUMN menus.for_date IS 'Date the menu is for (household timezone).';

COMMENT ON COLUMN menus.generated_at IS 'When the menu was generated (UTC).';

COMMENT ON COLUMN menus.notes IS 'Optional free-text notes.';

COMMENT ON TABLE menus IS 'Generated menus (tonight + planned).';

COMMENT ON COLUMN recipe_equipment.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_equipment.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_equipment.position IS 'Display order.';

COMMENT ON COLUMN recipe_equipment.text IS 'Equipment item.';

COMMENT ON TABLE recipe_equipment IS 'Equipment needed for the recipe, ordered by position.';

COMMENT ON COLUMN recipe_food_groups.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_food_groups.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_food_groups.food_group IS 'Food group: vegetables|fruit|grains|dairy|protein.';

COMMENT ON COLUMN recipe_food_groups.servings IS 'Servings of that food group.';

COMMENT ON TABLE recipe_food_groups IS 'Food-group servings a recipe contributes (soft nutrition targets).';

COMMENT ON COLUMN recipe_hazards.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_hazards.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_hazards.flag IS 'Hazard flag label.';

COMMENT ON TABLE recipe_hazards IS 'Safety hazard flags on a recipe (e.g. choking risk).';

COMMENT ON COLUMN recipe_nutrition.recipe_id IS 'Owning recipe (PK + FK, cascade delete).';

COMMENT ON COLUMN recipe_nutrition.energy_kcal IS 'Energy (kcal) per serving.';

COMMENT ON COLUMN recipe_nutrition.protein_g IS 'Protein (g) per serving.';

COMMENT ON COLUMN recipe_nutrition.fat_g IS 'Fat (g) per serving.';

COMMENT ON COLUMN recipe_nutrition.carbs_g IS 'Carbohydrate (g) per serving.';

COMMENT ON COLUMN recipe_nutrition.fibre_g IS 'Fibre (g) per serving.';

COMMENT ON COLUMN recipe_nutrition.iron_mg IS 'Iron (mg) per serving.';

COMMENT ON COLUMN recipe_nutrition.calcium_mg IS 'Calcium (mg) per serving.';

COMMENT ON COLUMN recipe_nutrition.sodium_mg IS 'Sodium (mg) per serving.';

COMMENT ON TABLE recipe_nutrition IS 'Per-serving nutrition for a recipe (1:1 with recipes).';

COMMENT ON COLUMN recipe_steps.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_steps.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_steps.position IS 'Step order.';

COMMENT ON COLUMN recipe_steps.text IS 'Step instruction text.';

COMMENT ON TABLE recipe_steps IS 'Method steps (one action per row), ordered by position.';

COMMENT ON COLUMN recipe_stickers.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_stickers.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_stickers.content IS 'Handwritten note (<=280 chars).';

COMMENT ON COLUMN recipe_stickers.target_section IS 'Pinned section: ingredients|equipment|method|tips, else general (optional).';

COMMENT ON COLUMN recipe_stickers.target_step_id IS 'Pinned Method step (FK; SET NULL on delete demotes the note to general).';

COMMENT ON COLUMN recipe_stickers.created_at IS 'Row creation timestamp (UTC).';

COMMENT ON COLUMN recipe_stickers.updated_at IS 'Last update timestamp (UTC).';

COMMENT ON TABLE recipe_stickers IS 'Post-cook handwritten notes pinned to a recipe / section / Method step.';

COMMENT ON COLUMN recipe_tags.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_tags.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_tags.tag IS 'Tag label.';

COMMENT ON TABLE recipe_tags IS 'Free-form tags on a recipe.';

COMMENT ON COLUMN recipe_tips.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipe_tips.recipe_id IS 'Owning recipe (FK, cascade delete).';

COMMENT ON COLUMN recipe_tips.position IS 'Display order.';

COMMENT ON COLUMN recipe_tips.text IS 'Tip text.';

COMMENT ON TABLE recipe_tips IS 'Cooking tips for the recipe, ordered by position.';

COMMENT ON COLUMN recipes.id IS 'Surrogate primary key.';

COMMENT ON COLUMN recipes.title IS 'Dish name; deduped case-insensitively.';

COMMENT ON COLUMN recipes.min_age_months IS 'Minimum toddler age (months) the recipe suits.';

COMMENT ON COLUMN recipes.texture IS 'Texture note, e.g. ''soft mash'' (optional).';

COMMENT ON COLUMN recipes.source IS 'Origin of the recipe: seed | llm | manual.';

COMMENT ON COLUMN recipes.approved IS 'In the cookbook / auto-suggestable.';

COMMENT ON COLUMN recipes.cooked IS 'Has been eaten (drives history); not auto-suggested on its own.';

COMMENT ON COLUMN recipes.created_at IS 'Row creation timestamp (UTC).';

COMMENT ON TABLE recipes IS 'Validated toddler dinner recipes; the cookbook + generation store.';

COMMENT ON COLUMN shopping_items.id IS 'Surrogate primary key.';

COMMENT ON COLUMN shopping_items.shopping_list_id IS 'Owning shopping list (FK, cascade delete).';

COMMENT ON COLUMN shopping_items.name IS 'Item name.';

COMMENT ON COLUMN shopping_items.quantity IS 'Quantity to buy.';

COMMENT ON COLUMN shopping_items.unit IS 'Unit for the quantity.';

COMMENT ON COLUMN shopping_items.est_unit_cost IS 'Estimated unit cost (future; unused in v1).';

COMMENT ON COLUMN shopping_items.est_total_cost IS 'Estimated total cost (future; unused in v1).';

COMMENT ON COLUMN shopping_items.store IS 'Store name (future; unused in v1).';

COMMENT ON COLUMN shopping_items.on_special IS 'Whether it''s on special (future; unused in v1).';

COMMENT ON TABLE shopping_items IS 'Items on a shopping list. Cost/store/on_special reserved for future supermarket integration.';

COMMENT ON COLUMN shopping_lists.id IS 'Surrogate primary key.';

COMMENT ON COLUMN shopping_lists.menu_id IS 'Source menu (FK; SET NULL on delete; optional).';

COMMENT ON COLUMN shopping_lists.budget IS 'Budget cap (future; unused in v1).';

COMMENT ON COLUMN shopping_lists.estimated_total IS 'Estimated total cost (future; unused in v1).';

COMMENT ON COLUMN shopping_lists.generated_at IS 'When the list was generated (UTC).';

COMMENT ON TABLE shopping_lists IS 'Groceries lists linked to a menu. budget/estimated_total reserved for future supermarket integration.';

UPDATE alembic_version SET version_num='e158a335e2f2' WHERE alembic_version.version_num = 'e5f6a7b8c9d0';

COMMIT;

