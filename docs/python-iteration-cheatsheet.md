# Python Iteration Cheat Sheet

> Quick lookup for the 3 ways to filter / transform a sequence.
> Example data: `exp = 1, 2, 3, 4` (a tuple)

## Decision table (pick one)

| Situation | Use |
|---|---|
| Simple logic, want **all values now** | **List comp** `[]` — default ⭐ |
| Simple logic, **huge / streaming** data, one pass | **Genexp** `()` |
| **Complex logic** (try/except, with, state) or reusable named unit | **`yield` function** |

## 1. List comprehension `[ ]` — the default

**Concept:** eager. Builds the whole list immediately. O(n) memory. **Fastest** (dedicated CPython bytecode).

```python
# FILTER — keep some elements (count shrinks): if goes at the END
odds = [x for x in exp if x % 2 == 1]           # [1, 3]

# TRANSFORM — change every element (count same): if/else goes at the FRONT
tra  = [x + 1 if x % 2 == 1 else x for x in exp] # [2, 2, 4, 4]
```

⚠️ Two `if` positions = two meanings — don't mix them up:
- `[f(x) if cond else g(x) for x in ...]` → ternary, picks the **value** (all elements kept)
- `[x for x in ... if cond]` → filter, drops **elements**

## 2. Generator expression `( )` — lazy version

**Concept:** same syntax, round brackets. Builds **nothing** until consumed; produces one value at a time. O(1) memory — works for huge/infinite input.

```python
gen = (x for x in exp if x % 2 == 1)   # nothing computed yet

# consume by:
list(gen)      # [1, 3]      materialize
sum(gen)       # 4           reduce
next(gen)      # 1           pull one
for x in gen:  ...           loop
```

⚠️ **Gotchas:**
- **One-shot**: after consuming, it's empty (`list(gen)` again → `[]`). Recreate to reuse.
- **No `len(gen)`, no `gen[0]`** — values don't exist yet.
- Wrapping in `list()` makes it eager again (laziness only pays if you *don't* materialize).

## 3. `yield` function — complex / reusable

**Concept:** any function containing `yield` is a **generator factory**. Calling it runs **nothing**. Each `yield` = pause point: hand out one value and **freeze all local state**; resume on next pull.

```python
def transfer_odd(seq):
    for x in seq:
        if x % 2 == 1:
            yield x + 1
        else:
            yield x

tra = list(transfer_odd(exp))   # [2, 2, 4, 4]
```

Use when logic needs what one expression can't hold:

```python
def parse_lines(lines):
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue                    # multiple skips
        try:
            yield parse(line)
        except ValueError:
            log.warning('bad: %r', line)  # try/except — impossible in a comp
```

## Comparison

| | List comp | Genexp | yield func |
|---|---|---|---|
| Creates | list (now) | generator | generator |
| Eager/lazy | eager | lazy | lazy |
| Memory | O(n) | O(1) | O(1) |
| Speed (measured, 1000 elems) | **1.00x fastest** | 1.07–1.28x | 1.24–1.39x |
| Code size | 1 line | 1 line | 4+ lines |
| Complex logic | ❌ | ❌ | ✅ |

Speed gap is small (~1.2–1.4x) — choose by **readability & memory**, not speed.

## Related: iterating a dict

```python
for k in d:            # KEYS only (default!)
for v in d.values():   # values
for k, v in d.items(): # (key, value) tuples — unpack; NO .value/.key attrs
```

⚠️ `for x in d` gives keys, and keys have no `.value` → `AttributeError`.
