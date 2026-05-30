<div align="center">

# Arm Calibration Guide

</div>

## Why calibration is needed

`GRID_XY` in `tictactoe_pi.py` maps each of the 9 board cells to an (X, Y) position
in millimetres in the arm's coordinate system. The defaults are estimates — you must
set them to match your physical paper placement before playing.

## Step-by-step

1. Place your paper flat in front of the arm in an area it can reach.
   Rule a 3×3 grid with cells roughly 40–50 mm wide.

2. Run your working arm-control script and jog the pencil tip over cell 0 (top-left).

3. Note the angles (`base`, `shoulder`, `elbow`) from the console output.

4. Convert to mm coordinates in a Python shell:
   ```python
   from arm import Arm
   a = Arm()
   coords = a.angleToCoordinata([base, shoulder, elbow])
   print(coords)  # → [x_mm, y_mm, z_mm]
   ```

5. Record the X and Y values. Repeat for all 9 cells.

6. Update `GRID_XY` in `tictactoe_pi.py`:
   ```python
   GRID_XY = {
       0: (-40, 200),   # your measured value
       1: (  0, 200),
       ...
   }
   ```

## Setting PEN_DOWN_Z

Start at `5` and lower by 1 until the pencil leaves a mark. Too low and the arm
will bind and skip steps. Typically 0–3 mm works.

## Tilted paper

If your paper isn't perfectly level use `arm.setPlaneXZ()` and `arm.setPlaneYZ()`
(built into `Arm.py`) to apply a Z offset correction across the drawing plane.
