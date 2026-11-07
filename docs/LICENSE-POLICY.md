# Dependency license policy

The project is licensed Apache-2.0. Existing organizational exclusions apply to
shipped, test-only and build-only dependencies incorporated into the project.
This source cleanup does not change the license policy.

| License | Status |
|---|---|
| MIT | Allowed |
| Apache-2.0 | Allowed |
| BSL-1.0 | Allowed |
| Public domain / Unlicense / CC0 | Allowed |
| BSD-2-Clause | Excluded |
| BSD-3-Clause | Excluded |
| Copyleft (GPL / LGPL / AGPL / MPL) | Excluded |

The BSD exclusions are organizational policy, not a claim of incompatibility
with Apache-2.0. Reversing them requires an explicit policy decision. Review
licenses and notices before introducing dependencies, including test tools.
Keep the pinned Rust dependency inventories and package/toolchain notices used
by the offline bundle. External host/runtime prerequisites retain their own
licenses; do not strip their notices or misrepresent their provenance.
