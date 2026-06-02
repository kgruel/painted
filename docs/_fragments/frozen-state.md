All state types are frozen — immutable dataclasses. State is created through its
constructor and updated with `dataclasses.replace()`, which returns *new* state; it is
never mutated in place. Rendering is a pure function of that state —
`render_fn(state, ...) → Block`: same inputs, same output, no side effects.
