# Dependency declarations

One entry per dependency, at one definition site. A capability's own degraded
declaration is co-located with the capability and names the dependency by the
same identifier; the remedy — what would provide the dependency — is stated
here once rather than repeated in every capability that needs it.

Identifiers are dotted and two-level: the product root alone, or the product
root followed by a covered Module. They are looked up in the pin declaration's
declared scope, never invented here.

**No version scope is written in this file.** A pin's coverage is read from the
pin declaration; a version restated here would be a claim about current reality
that does not carry its pin.

<!-- ai-memory:dependency-declaration
dependency: bmad
upstream_source: https://github.com/bmad-code-org/BMAD-METHOD
ai-memory:end-dependency-declaration -->
