---------------------------- MODULE HostAdapter ----------------------------
(* A model of ViewportAdapter's ticket + frame-token protocol
   (src/painted/host.py, HOST_RUNG_DESIGN §6).

   Each action is one method call on the frozen adapter value. The adapter is
   pure, so one call is one indivisible step; everything between calls is the
   host's interleaving, which is what this model explores.

   What is abstracted, and why that is sound for the two safety properties:
     - the anchor policy and all clamping: Publish and Resize may land on ANY
       offset, a superset of what the code can choose;
     - Block contents: a block is an opaque value from Contents;
     - RenderKey: one integer, the version of the renderer inputs. *)
EXTENDS Naturals

CONSTANTS
    Branches,    \* frozen adapter values alive at once (pure forks)
    MaxKey,      \* renderer-input versions 1..MaxKey
    MaxGid,      \* plan() calls explored
    Contents,    \* distinct rendered Blocks
    Offsets,     \* viewport offsets
    Heights,     \* frame heights F
    TicketReuse  \* TRUE: a Plan may be published more than once (it is a
                 \* frozen value; nothing in the adapter consumes it)

VARIABLES
    desired,    \* the host's current renderer-input version
    adapter,    \* [Branches -> adapter value]
    nextGid,    \* models object identity: each plan() mints a fresh _GenerationId
    plans,      \* outstanding Plan tickets
    shown,      \* the last displayed Frame: its token, and what it really mapped
    regressed   \* history: some publish installed older inputs over newer ones

vars == <<desired, adapter, nextGid, plans, shown, regressed>>

NoGen   == 0                       \* generation is None
NoFrame == [tok |-> <<>>, map |-> <<>>]

Empty == [gid |-> NoGen, key |-> 0, content |-> "none", off |-> 0,
          F |-> CHOOSE h \in Heights : TRUE]

\* ViewportAdapter._token: generation identity + offset + frame height.
Token(a)   == <<a.gid, a.off, a.F>>
\* What a frame coordinate actually translates through (resolve/_content_hit).
Mapping(a) == <<a.content, a.off, a.F>>

Init ==
    /\ desired = 1
    /\ adapter = [b \in Branches |-> Empty]
    /\ nextGid = 1
    /\ plans = {}
    /\ shown = NoFrame
    /\ regressed = FALSE

\* The renderer inputs change (data, fidelity, width).
InputsChange ==
    /\ desired < MaxKey
    /\ desired' = desired + 1
    /\ UNCHANGED <<adapter, nextGid, plans, shown, regressed>>

\* ViewportAdapter.plan(key): ticket = (base, proposed), proposed fresh per call.
Plan(b) ==
    /\ nextGid <= MaxGid
    /\ plans' = plans \cup {[key |-> desired, base |-> adapter[b].gid, gid |-> nextGid]}
    /\ nextGid' = nextGid + 1
    /\ UNCHANGED <<desired, adapter, shown, regressed>>

\* ViewportAdapter.publish(content, plan, frame_height=...), the accepted arm.
\* The rejected arm returns None and changes nothing, so it is not an action.
Publish(b, p, c, o, h) ==
    /\ p.base = adapter[b].gid                                  \* GUARD: ticket base
    /\ adapter' = [adapter EXCEPT ![b] =
           [gid |-> p.gid, key |-> p.key, content |-> c, off |-> o, F |-> h]]  \* STAMP
    /\ regressed' = (regressed \/ p.key < adapter[b].key)
    /\ plans' = IF TicketReuse THEN plans ELSE plans \ {p}
    /\ UNCHANGED <<desired, nextGid, shown>>

\* scroll / page_up / page_down / home / end / scroll_to / scroll_into_view.
Scroll(b, o) ==
    /\ o # adapter[b].off
    /\ adapter' = [adapter EXCEPT ![b].off = o]
    /\ UNCHANGED <<desired, nextGid, plans, shown, regressed>>

\* ViewportAdapter.resize(F): same generation, re-windowed and re-clamped.
Resize(b, h, o) ==
    /\ h # adapter[b].F
    /\ adapter' = [adapter EXCEPT ![b].F = h, ![b].off = o]
    /\ UNCHANGED <<desired, nextGid, plans, shown, regressed>>

\* ViewportAdapter.frame(): the host paints it and keeps the token
\* (HostViewport.frame sets last_token).
Frame(b) ==
    /\ shown' = [tok |-> Token(adapter[b]), map |-> Mapping(adapter[b])]
    /\ UNCHANGED <<desired, adapter, nextGid, plans, regressed>>

\* The adapter is a frozen value: holding a second reference is a pure fork.
Fork(from, to) ==
    /\ from # to
    /\ adapter[from] # adapter[to]
    /\ adapter' = [adapter EXCEPT ![to] = adapter[from]]
    /\ UNCHANGED <<desired, nextGid, plans, shown, regressed>>

\* Named, so TLC reports each step by its action and not as "Next".
DoPlan    == \E b \in Branches : Plan(b)
DoPublish == \E b \in Branches, p \in plans, c \in Contents, o \in Offsets, h \in Heights :
                 Publish(b, p, c, o, h)
DoScroll  == \E b \in Branches, o \in Offsets : Scroll(b, o)
DoResize  == \E b \in Branches, h \in Heights, o \in Offsets : Resize(b, h, o)
DoFrame   == \E b \in Branches : Frame(b)
DoFork    == \E from \in Branches, to \in Branches : Fork(from, to)

Next == InputsChange \/ DoPlan \/ DoPublish \/ DoScroll \/ DoResize \/ DoFrame \/ DoFork

Spec == Init /\ [][Next]_vars

----------------------------------------------------------------------------
\* P1. A publish that lost the race never installs older renderer inputs over
\*     newer ones. Harm if broken: the screen settles on a stale render with no
\*     work outstanding to replace it.
NoRegress == ~regressed

\* P2. A pointer event resolves (resolve() returns non-stale) only against an
\*     adapter that maps coordinates exactly as the painted frame did - on any
\*     branch. Harm if broken: a click selects a row the user was not shown.
StaleHitsDrop ==
    shown # NoFrame =>
        \A b \in Branches :
            Token(adapter[b]) = shown.tok => Mapping(adapter[b]) = shown.map
=============================================================================
