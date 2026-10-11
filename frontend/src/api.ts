import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

export type CookingStep = {
  id: string;
  sequence: number;
  title: string;
  instruction: string;
  duration_minutes: number;
  status: 'pending' | 'ready' | 'in_progress' | 'completed' | 'blocked';
  requires_physical_confirmation: boolean;
  timers: { deadline_at: string; status: string }[];
};

export type Dish = { id: string; name: string; status: string; steps: CookingStep[] };
export type Meal = {
  id: string;
  name: string;
  status: string;
  target_serving_at: string;
  dishes: Dish[];
  progress: { completed: number; total: number; fraction: number };
  next_action: { action: { step_id: string; dish: string; title: string; instruction?: string; estimated_minutes?: number } | null; reason: string; clarification_required: boolean; question?: string };
  recent_events: { type: string; payload: Record<string, unknown>; created_at: string | null }[];
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-Demo-User': 'demo-user', ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.detail?.message || payload?.detail || `Request failed (${response.status})`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json() as Promise<T>;
}

export const api = {
  meals: () => request<{ id: string; name: string; status: string; target_serving_at: string }[]>('/api/v1/meals'),
  meal: (id: string) => request<Meal>(`/api/v1/meals/${id}/status`),
  createMeal: (body: unknown) => request<Meal>('/api/v1/meals', { method: 'POST', body: JSON.stringify(body) }),
  complete: (mealId: string, stepId: string, physicalConditionConfirmed = false) => request(`/api/v1/meals/${mealId}/steps/${stepId}/complete`, { method: 'POST', body: JSON.stringify({ physical_condition_confirmed: physicalConditionConfirmed }) }),
  loadDemo: () => request<Meal>('/api/v1/demo/load', { method: 'POST' }),

  resetDemo: () => request<{ status: string; deleted_demo_meals: number }>('/api/v1/demo/reset', { method: 'POST' }),
};

export function demoMealPayload() {
  const target = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  return {
    name: 'Dal, rice & aloo sabzi', target_serving_at: target,
    dishes: [
      { name: 'Rice', steps: [
        { title: 'Wash rice', instruction: 'Rinse rice until the water is clearer.', duration_minutes: 3, depends_on: [] },
        { title: 'Cook rice', instruction: 'Cook using your usual method. Confirm the current physical conditions first.', duration_minutes: 18, depends_on: [0], requires_physical_confirmation: true },
        { title: 'Rest rice', instruction: 'Let the rice rest and check its texture.', duration_minutes: 5, depends_on: [1] },
      ] },
      { name: 'Dal', steps: [
        { title: 'Rinse dal', instruction: 'Rinse the dal.', duration_minutes: 2, depends_on: [] },
        { title: 'Pressure cook dal', instruction: 'Follow the pressure cooker instructions. Never open it while pressurized.', duration_minutes: 20, depends_on: [0], requires_physical_confirmation: true },
        { title: 'Temper dal', instruction: 'Prepare tempering carefully and combine with the dal.', duration_minutes: 5, depends_on: [1] },
      ] },
      { name: 'Aloo sabzi', steps: [
        { title: 'Chop potatoes', instruction: 'Wash and chop potatoes.', duration_minutes: 8, depends_on: [] },
        { title: 'Sauté spices', instruction: 'Heat oil carefully and sauté spices.', duration_minutes: 3, depends_on: [0], requires_physical_confirmation: true },
        { title: 'Cook potatoes', instruction: 'Cook until done; elapsed time alone is not proof.', duration_minutes: 15, depends_on: [1], requires_physical_confirmation: true },
      ] },
    ],
  };
}

export async function callMcpTool<T>(name: string, args: Record<string, unknown>): Promise<T> {
  const client = new Client({ name: 'rasoi-relay-web', version: '0.1.0' });
  const transport = new StreamableHTTPClientTransport(new URL(`${API_BASE}/mcp/`));
  await client.connect(transport);
  try {
    const result = await client.callTool({ name, arguments: args });
    if (result.isError) throw new Error(`MCP tool ${name} returned an error`);
    const structured = (result as { structuredContent?: T }).structuredContent;
    if (structured !== undefined) return structured;
    const textResult = result.content.find((item) => item.type === 'text');
    if (textResult?.type === 'text') {
      try { return JSON.parse(textResult.text) as T; } catch { return textResult.text as T; }
    }
    return result as T;
  } finally {
    await client.close();
  }
}
