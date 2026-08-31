import { useEffect, useState } from "react";

import { getIngredients, type Ingredient } from "../api/restaurant";

export function InventoryDashboard() {
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void getIngredients()
      .then((items) => active && setIngredients(items))
      .catch(() => active && setError("Unable to load ingredients."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  return (
    <section>
      <p className="eyebrow">Inventory</p>
      <h1>Ingredients</h1>
      {loading && <p>Loading ingredients…</p>}
      {error && <p className="status error">{error}</p>}
      {!loading && !error && (
        <div className="grid">
          {ingredients.map((ingredient) => (
            <article className="panel" key={ingredient.ingredient_id}>
              <strong>{ingredient.ingredient_name}</strong>
              <p>{ingredient.ingredient_code}</p>
              <span>Minimum stock: {ingredient.minimum_stock_qty}</span>
            </article>
          ))}
          {ingredients.length === 0 && <p>No ingredients found.</p>}
        </div>
      )}
    </section>
  );
}
