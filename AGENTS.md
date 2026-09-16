# Weather Lab maintenance

Follow the parent SupahTrade operating instructions. Do not spawn subagents.

Whenever a change affects architecture, update the corresponding UML diagrams and architecture documentation in the same change:

- Update `docs/ARCHITECTURE-UML.md` and the affected component definitions in `docs/architecture/render.py`.
- Regenerate the SVG figures and offline gallery with `python docs/architecture/render.py`.
- Verify diagram rendering and actual call order, including conditional paths, evidence availability, model budgets and execution boundaries.
- Distinguish implemented connections from optional or unconnected integrations. Keep versioned protocol differences explicit.
- Rebuild distributable ZIPs when their included runtime or documentation changes. Include updated documentation in the authorized repository update.

Keep acquisition details out of the README as requested. Put source methodology and limitations in the relevant research documentation.

## Current user priority

After completing the previous-weeks archive update, freeze frontend changes. Focus on profitability research using existing data, configuration and isolated experiments. Do not resume frontend design or feature work without a new user instruction. Preserve all costs and report negative results; never label NOAA archives as historical Apple forecasts.
