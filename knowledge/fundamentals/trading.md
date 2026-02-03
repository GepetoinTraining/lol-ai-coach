# Trading & Spacing Fundamentals

## The Tethering Axiom (Dynamic Spacing)

**Tethering** is the law governing the safe and aggressive distance between two champions. It's defined as a function of distance and reaction time.

### Core Concept:
Every champion has a "threat bubble" or zone of influence, with radius determined by:
- Range of their highest-impact ability
- Auto-attack range
- Distance they can travel during opponent's reaction time

### The Formula:
```
Safe Distance (d) = Enemy Ability Range + (Enemy Movement Speed × Your Reaction Time)
```

Elite players operate at the **edge** of this zone, staying just outside enemy range while applying maximum pressure.

## Input Buffering

**Input Buffering** is the technical process of queuing a command during a previous action's animation, ensuring the next action occurs on the first possible frame.

### Benefits:
- Eliminates visual reaction delay
- Transfers execution load from reaction to planning
- Creates frame-perfect combos

### Examples:
- Flash → Q buffered (ability queued before flash animation ends)
- Auto → Ability reset → Auto

## Animation Canceling

All actions consist of three phases:
1. **Wind-up** (Start)
2. **Active** (Effect triggers)
3. **Recovery** (End lag)

### Optimization:
Cancel the **recovery phase** through movement commands or other abilities as soon as the effect triggers (Active phase).

### Common Cancels:
| Champion | Cancel | Input |
|----------|--------|-------|
| Riven | Q → AA → Move | Right-click between each |
| ADCs | AA → Move → AA | Orbwalking/Kiting |
| Vayne | AA → Q → AA | Tumble reset |

## Trading Patterns

### Favorable Trade Conditions:
- Enemy used key ability (on cooldown)
- You have minion advantage
- Enemy is locked in CS animation
- Your ability comes off cooldown first

### Unfavorable Trade Conditions:
- Your wave is smaller
- Enemy has level advantage
- You're about to hit power spike (wait for it)
- No vision and jungle could be nearby
