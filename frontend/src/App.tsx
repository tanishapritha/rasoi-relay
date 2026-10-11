import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, Check, ChefHat, CircleHelp, Clock3, Flame, Leaf, MessageCircle, Mic, Pause, Play, RotateCcw, ShieldCheck, Sparkles, Utensils, Waves } from 'lucide-react';
import { api, demoMealPayload, type Meal } from './api';

export default function App() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState('');
  const [message, setMessage] = useState('I’m back. Kya karna hai ab?');
  const [assistantReply, setAssistantReply] = useState('Your cooking context will appear here after you load a meal and recover it.');
  const [toolActivity, setToolActivity] = useState<{ tool: string; input: unknown; output: unknown } | null>(null);
  const mealsQuery = useQuery({ queryKey: ['meals'], queryFn: api.meals });
  const mealQuery = useQuery({ queryKey: ['meal', selectedId], queryFn: () => api.meal(selectedId), enabled: Boolean(selectedId), refetchInterval: 15000 });
  const meal = mealQuery.data as Meal | undefined;
  const refresh = async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: ['meals'] });
    if (id) await queryClient.invalidateQueries({ queryKey: ['meal', id] });
  };
  const startMutation = useMutation({ mutationFn: () => api.createMeal(demoMealPayload()), onSuccess: async (data) => { setSelectedId(data.id); await refresh(data.id); setAssistantReply('Dinner is set up. Your progress will be saved by the backend.'); } });
  const completeMutation = useMutation({ mutationFn: ({ mealId, stepId }: { mealId: string; stepId: string }) => api.complete(mealId, stepId), onSuccess: async (_, vars) => refresh(vars.mealId) });
  const interruptionMutation = useMutation({ mutationFn: (id: string) => api.interrupt(id), onSuccess: async (data, id) => { await refresh(id); setAssistantReply('Interruption saved. I will not assume the stove is off. Please confirm its current state before resuming.'); setToolActivity({ tool: 'report_interruption (REST demo action)', input: { meal_id: id, reason: 'phone call', stove_state: 'unknown', simulated: true }, output: data }); } });
  const recoveryMutation = useMutation({ mutationFn: (id: string) => api.recover(id), onSuccess: async (data, id) => { await refresh(id); setToolActivity({ tool: 'recover_meal (REST service)', input: { meal_id: id }, output: data }); const unknown = Array.isArray(data.unknown_conditions) && data.unknown_conditions.length > 0; setAssistantReply(unknown ? 'I have your last confirmed progress. The stove state is unknown, so please check it and confirm before we continue.' : 'I recovered your saved progress. Let’s continue with the next eligible step.'); } });
  const resetMutation = useMutation({ mutationFn: api.resetDemo, onSuccess: async () => { setSelectedId(''); setToolActivity(null); setAssistantReply('Demo data cleared. Load a fresh meal to replay the flow.'); await queryClient.invalidateQueries(); } });
  const nextAction = meal?.next_action?.action;
  const stepsCompleted = meal?.progress.completed ?? 0;
  const stepsTotal = meal?.progress.total ?? 0;
  const servingTime = useMemo(() => meal ? new Date(meal.target_serving_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—', [meal]);
  const handleSend = () => {
    const normalized = message.toLowerCase();
    if (!meal) { setAssistantReply('Load the demo meal first so I can use a real saved cooking state.'); return; }
    if (normalized.includes('back') || normalized.includes('next') || normalized.includes('kya') || normalized.includes('recover')) recoveryMutation.mutate(meal.id);
    else if (normalized.includes('interrupt') || normalized.includes('phone')) interruptionMutation.mutate(meal.id);
    else setAssistantReply('I can recover your meal or record an interruption in this local demo. Core actions are deterministic; full natural-language AI routing is not connected yet.');
  };

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><ChefHat size={22} /></div><div><strong>rasoi relay</strong><span>your kitchen companion</span></div></div>
      <div className="side-label">YOUR KITCHEN</div>
      <button className="nav-item active"><Utensils size={17} /> Cooking dashboard</button>
      <button className="nav-item" onClick={() => recoveryMutation.mutate(selectedId)} disabled={!selectedId}><Waves size={17} /> Recovery mode</button>
      <div className="sidebar-bottom"><div className="demo-note"><span className="live-dot"/> <div><strong>Demo environment</strong><small>Alexa+ experience simulated</small></div></div><p>Progress is saved by the backend. Physical conditions are never inferred.</p></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><span className="eyebrow">SUNDAY, IN YOUR KITCHEN</span><h1>Let’s get dinner back on track.</h1><p>Pick up where you left off. We’ll remember the details.</p></div><div className="top-actions"><span className="status-pill"><span className="live-dot"/> Local demo</span><button className="icon-button" title="Reset demo" onClick={() => resetMutation.mutate()}><RotateCcw size={17}/></button></div></header>
      {mealsQuery.isError && <div className="error-banner"><AlertTriangle size={18}/><span>Could not reach the API. Start FastAPI and check VITE_API_BASE_URL.</span></div>}
      {!meal && <section className="welcome-card"><div className="welcome-copy"><span className="eyebrow">A LITTLE LESS MENTAL LOAD</span><h2>Your meal, right where you left it.</h2><p>Load a reproducible dinner plan to explore saved progress, interruptions and safe recovery.</p><button className="primary-button" onClick={() => startMutation.mutate()} disabled={startMutation.isPending}><Play size={16}/>{startMutation.isPending ? 'Preparing dinner…' : 'Load demo dinner'}<ArrowRight size={16}/></button>{startMutation.isError && <p className="error-text">{(startMutation.error as Error).message}</p>}</div><div className="welcome-illustration"><div className="plate"><div className="food food-dal"/><div className="food food-rice"/><div className="food food-sabzi"/></div><span className="herb herb-one">✳</span><span className="herb herb-two">✦</span></div></section>}
      {meal && <>
        <section className="meal-summary"><div className="meal-heading"><div className="meal-icon"><Utensils size={20}/></div><div><span className="eyebrow">TONIGHT’S MENU</span><h2>{meal.name}</h2><span className="muted">{stepsCompleted} of {stepsTotal} steps confirmed</span></div></div><div className="serve-time"><span>Target serving</span><strong><Clock3 size={17}/>{servingTime}</strong><small>Estimate, not a guarantee</small></div></section>
        <div className="progress-track"><span style={{ width: `${meal.progress.fraction * 100}%` }}/></div>
        <section className="content-grid"><div className="left-column"><div className="section-heading"><div><span className="eyebrow">IN PROGRESS</span><h2>On the stove</h2></div><span className="count-pill">{meal.dishes.length} dishes</span></div>
          <div className="dish-list">{meal.dishes.map((dish, index) => { const done = dish.steps.filter(step => step.status === 'completed').length; const firstOpen = dish.steps.find(step => step.status !== 'completed'); return <article className="dish-card" key={dish.id}><div className={`dish-art dish-art-${index}`}><span>{index === 0 ? '◉' : index === 1 ? '◌' : '✿'}</span></div><div className="dish-body"><div className="dish-title-row"><h3>{dish.name}</h3><span className="step-count">{done}/{dish.steps.length}</span></div><div className="mini-progress"><span style={{ width: `${done / dish.steps.length * 100}%` }}/></div>{firstOpen ? <p className="next-step"><span className="step-dot"/>Next: {firstOpen.title}</p> : <p className="next-step done"><Check size={14}/> All steps complete</p>}<div className="step-stack">{dish.steps.map(step => <div className={`step-row ${step.status === 'completed' ? 'step-complete' : ''}`} key={step.id}><span className="step-status">{step.status === 'completed' ? <Check size={13}/> : <span/>}</span><div className="step-copy"><strong>{step.title}</strong><small>{step.duration_minutes} min estimate{step.requires_physical_confirmation ? ' · confirmation required' : ''}</small></div>{step.status !== 'completed' && <button className="complete-button" disabled={completeMutation.isPending || step.status === 'blocked'} onClick={() => completeMutation.mutate({ mealId: meal.id, stepId: step.id })}>Done</button>}</div>)}</div></div></article>; })}</div>
        </div><div className="right-column"><section className="next-card"><div className="next-card-top"><span className="eyebrow">YOUR NEXT MOVE</span><span className="sparkle"><Sparkles size={16}/></span></div>{nextAction ? <><h3>{nextAction.title}</h3><p className="dish-tag">{nextAction.dish}</p><p>{nextAction.instruction || 'Confirm prerequisites before proceeding.'}</p>{meal.next_action.clarification_required && <div className="warning-note"><CircleHelp size={17}/><span>{meal.next_action.question || 'Please confirm the current physical conditions.'}</span></div>}<div className="next-meta"><span><Clock3 size={15}/> {nextAction.estimated_minutes ?? '—'} min estimate</span><span><ShieldCheck size={15}/> State-aware</span></div><button className="primary-button full" onClick={() => recoveryMutation.mutate(meal.id)}><Waves size={16}/> Recover my place</button></> : <><h3>All steps are complete</h3><p>Check the dishes and confirm food is ready before serving.</p></>}</section>
          <section className="recovery-card"><div className="recovery-icon"><Pause size={18}/></div><div><h3>Got interrupted?</h3><p>Your progress stays saved. Unknown conditions stay unknown.</p></div><button className="secondary-button" onClick={() => interruptionMutation.mutate(meal.id)} disabled={interruptionMutation.isPending}>Simulate interruption</button></section>
          <section className="assistant-card"><div className="assistant-heading"><div className="assistant-avatar"><MessageCircle size={17}/></div><div><h3>Ask Rasoi</h3><span><span className="live-dot"/> Context-aware demo</span></div></div><div className="chat-bubble">{assistantReply}</div><div className="quick-prompts"><button onClick={() => { setMessage('I’m back. Kya karna hai ab?'); setAssistantReply('Ready to recover your saved cooking state.'); }}>“I’m back”</button><button onClick={() => { setMessage('I got a phone call'); setAssistantReply('Ready to record an interruption.'); }}>“Got interrupted”</button></div><form className="chat-input" onSubmit={event => { event.preventDefault(); handleSend(); }}><input aria-label="Ask Rasoi" value={message} onChange={event => setMessage(event.target.value)} placeholder="Ask in English or Hinglish…"/><button type="button" className="mic-button" title="Voice input is optional and not connected in this build" onClick={() => setAssistantReply('Voice input is not connected yet. You can use text for the demo.')}><Mic size={17}/></button><button className="send-button" type="submit"><ArrowRight size={17}/></button></form></section>
          {toolActivity && <section className="tool-card"><div className="tool-card-heading"><Leaf size={16}/><strong>Tool activity</strong><span>REST service</span></div><p>{toolActivity.tool}</p><details><summary>Inspect request and response</summary><h4>Input</h4><pre>{JSON.stringify(toolActivity.input, null, 2)}</pre><h4>Output</h4><pre>{JSON.stringify(toolActivity.output, null, 2)}</pre></details></section>}
        </div></section>
      </>}
      <footer><span><Flame size={14}/> Made for real kitchens, not perfect memory.</span><span>Guidance only · Always confirm physical conditions</span></footer>
    </main>
  </div>;
}
