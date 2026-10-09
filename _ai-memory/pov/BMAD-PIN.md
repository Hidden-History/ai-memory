# BMAD pin declaration

The version scope of BMAD that this product expects, and the Modules that scope
covers. This is the one definition site: the installer reads it when it reports
that BMAD or a required Module is unavailable, and nothing else restates it.

This file states an **expectation of ours**. It is not a record of what is
installed on any machine — that record is BMAD's own, lives in the target
project, and is absent exactly when this file is needed.

**The covered Modules are bound to the pin, in the same block.** The pin is
BMAD's own release version, and that version covers only the Modules that ship
in BMAD's own repository. Every other Module is published from a separate
repository on its own version stream: it is outside this pin's coverage, and
nothing here describes it as pinned. Changing the pin means re-deriving the
covered Modules from the upstream repository at the new release, not editing one
line without the other.

Identifiers are dotted and two-level, the same notation
[DEPENDENCIES.md](DEPENDENCIES.md) uses: the product root alone, or the product
root followed by a covered Module. Where to obtain the dependency is stated
there, once, and is not repeated here.

<!-- ai-memory:pin-declaration
dependency: bmad
version_scope: 6.9.0
covers: bmad.core, bmad.bmm
ai-memory:end-pin-declaration -->
