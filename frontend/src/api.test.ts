import { describe, expect, it } from 'vitest';
import { demoMealPayload } from './api';

describe('demo meal fixture', () => {
  it('contains three dishes with ordered step dependencies', () => {
    const meal = demoMealPayload();
    expect(meal.dishes.map((dish) => dish.name)).toEqual(['Rice', 'Dal', 'Aloo sabzi']);
    for (const dish of meal.dishes) {
      dish.steps.forEach((step, index) => {
        expect(step.depends_on.every((dependency) => dependency >= 0 && dependency < index)).toBe(true);
      });
    }
  });

  it('marks physical confirmation requirements explicitly', () => {
    const meal = demoMealPayload();
    expect(meal.dishes.flatMap((dish) => dish.steps).some((step) => step.requires_physical_confirmation)).toBe(true);
  });
});
