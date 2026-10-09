# How a plate is drawn

- **Direction:** left to right. The trunk (paths with no variants) sits on the centre line.
- **Variants:** one diagram per workflow. Each variant leaves the trunk at its first route stage and rejoins at its last; branches stack above and below the trunk. Each variant gets a colour and a legend entry; shared trunk stays neutral.
- **Decisions:** diamond. Start and end: rounded pill. Steps: rectangle.
- **Bone labels:** each stage lists its files underneath in small monospace text (`stageFile.label`), owners first.
- **Shared systems:** a side rail on the plate; thin lines to the stages that use them.
- **Foundation:** a faded band along the bottom of the overview, grouped (Settings, Database connection, ...). Not drawn on individual plates.
- **Incomplete:** any stage or path with `status: incomplete` is drawn dotted; flags attach as a callout to their target.
- **Overview ("full body"):** one box per module, `links` drawn between them, each box links to its plate. Modules with `drawn: false` are greyed out.
