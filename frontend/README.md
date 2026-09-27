# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Plan drawing conventions (Issue #46)

The live floor-plan drawing is `src/design/DemoPlan.tsx`, composing `src/components/plan/*`. It
reads architecture ONLY from `app.demo.contract.DemoDesign` (mirrored as `src/design/demoDesign.ts`)
— see `DemoPlan.tsx`'s own module docstring: "This component decides NOTHING architectural... If a
fact is not on the object, it is not drawn." Full details and the authoritative test list live on
[`docs/wiki/features/interior-layout.md`](../docs/wiki/features/interior-layout.md) and
[`docs/wiki/features/wall-semantics.md`](../docs/wiki/features/wall-semantics.md); this section is
just the drawing-conventions summary:

- **Walls** (`components/plan/Walls.tsx`) are weighted and coloured by the backend's own semantic
  class (`wall_class`: EXTERIOR/INTERIOR/WET_SERVICE/PROTECTED) and real `thickness_m`.
- **Doors** (`components/plan/DoorSymbol.tsx`) draw the wall opening, the leaf and its swing arc
  from the engine's own `hinge_x`/`hinge_y`/`swing_deg` — never inferred from a room lookup.
- **Windows** are drawn only where the backend placed one, labelled with their real width.
- **Layout objects** (`components/plan/InteriorLayout.tsx`) draw the engine-placed furniture/fixture
  rectangles as-is, one per placed item.
- **Labels and dimensions** (`design/demoRoomLabel.ts`) print each room's name, its realized NET
  width × depth, and its authoritative area — always the numbers the backend computed, never a
  frontend recalculation.
- **North arrow** (`design/CompassRose.tsx`/`compass.ts`) is drawn only when the caller passes a
  known `streetFacingSide`; a design with no known orientation (or a thumbnail) draws none.
- **Scale bar** (`design/ScaleBar.tsx`) is a drawing CONVENTION, not an architectural fact — its
  length is a round metric step (1-2-5 series) picked from the drawing's own frame size, drawn
  alongside the compass and gated the same way so a thumbnail stays uncluttered.

`backend/tests/test_renderer_audit.py` statically audits that every one of the categories above is
drawn from a real `DemoDesign` field (never a renderer-invented literal), and that the compass and
scale bar are never drawn without the orientation/frame data they need.
