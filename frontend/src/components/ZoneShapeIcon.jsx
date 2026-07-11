import './ZoneShapeIcon.css';

/**
 * Renders a spell's area of effect as a small grid of squares — never
 * dots/circles, since Dofus's board is cell-based. This is a simplified
 * top-down square-grid representation (not the game's isometric diamond
 * board), chosen for clarity in a compact UI icon.
 *
 * Geometry is computed directly from the raw {type, shape, size} area
 * object already present in the data (see parse_spells.py). "cercle" is
 * a filled diamond because Dofus distance is Manhattan (|dx|+|dy|), which
 * is why an in-game "circular" zone reads as a diamond on a square grid.
 */

const GLOBAL_SIZE_THRESHOLD = 10; // area.size uses 63 as a "whole battlefield" sentinel

function computeCells(type, shape, size) {
  const n = size || 0;

  if (!type || type === 'point' || n === 0) {
    return { cells: [[0, 0]], radius: 1 };
  }
  if (n >= GLOBAL_SIZE_THRESHOLD) {
    return { global: true, radius: 2 };
  }

  const cells = [];
  const push = (x, y) => cells.push([x, y]);

  switch (type) {
    case 'cercle': {
      for (let dx = -n; dx <= n; dx++) {
        for (let dy = -n; dy <= n; dy++) {
          if (Math.abs(dx) + Math.abs(dy) <= n) push(dx, dy);
        }
      }
      break;
    }
    case 'croix': {
      const diagonal = shape === 88; // "X" diagonal cross vs orthogonal "+"
      for (let k = -n; k <= n; k++) {
        if (diagonal) {
          push(k, k);
          push(k, -k);
        } else {
          push(k, 0);
          push(0, k);
        }
      }
      break;
    }
    case 'ligne': {
      // Direction is chosen at cast time in-game; shown extending one way
      // from the origin for a clean, legible icon.
      for (let dx = 0; dx <= n; dx++) push(dx, 0);
      break;
    }
    case 'cône': {
      push(0, 0);
      for (let d = 1; d <= n; d++) {
        const half = Math.floor(d / 2);
        for (let dy = -half; dy <= half; dy++) push(d, dy);
      }
      break;
    }
    case 'anneau': {
      for (let dx = -n; dx <= n; dx++) {
        for (let dy = -n; dy <= n; dy++) {
          if (Math.abs(dx) + Math.abs(dy) === n) push(dx, dy);
        }
      }
      break;
    }
    default:
      push(0, 0);
  }

  // Dedupe
  const uniq = new Map();
  for (const [x, y] of cells) uniq.set(`${x},${y}`, [x, y]);
  return { cells: [...uniq.values()], radius: n };
}

const TYPE_CAPTION = {
  point: 'case unique',
  cercle: 'zone',
  croix: 'croix',
  ligne: 'ligne',
  cône: 'cône',
  anneau: 'anneau',
};

export function zoneCaption(type, size, shape) {
  const n = size || 0;
  if (!type || type === 'point' || n === 0) return null;
  if (n >= GLOBAL_SIZE_THRESHOLD) return 'zone globale';
  if (type === 'croix' && shape === 88) return `croix (X) r${n}`;
  return `${TYPE_CAPTION[type] || type} r${n}`;
}

export default function ZoneShapeIcon({ type, shape, size, className = '' }) {
  const result = computeCells(type, shape, size);
  const PX = 40; // fixed icon footprint — larger radii just get smaller squares

  if (result.global) {
    // Distinct "whole battlefield" pattern: fully tiled grid, no single
    // highlighted origin, communicating "everywhere" without a dot/circle.
    const dim = 5;
    const cell = PX / dim;
    const squares = [];
    for (let x = 0; x < dim; x++) {
      for (let y = 0; y < dim; y++) {
        squares.push(
          <rect
            key={`${x}-${y}`}
            x={x * cell}
            y={y * cell}
            width={cell - 1}
            height={cell - 1}
            className="zsi-cell zsi-cell--global"
          />
        );
      }
    }
    return (
      <svg viewBox={`0 0 ${PX} ${PX}`} className={`zsi-svg ${className}`} aria-hidden="true">
        {squares}
      </svg>
    );
  }

  const { cells, radius } = result;
  const dim = 2 * radius + 3; // margin cell on each side
  const cell = PX / dim;
  const affected = new Set(cells.map(([x, y]) => `${x},${y}`));

  const squares = [];
  const halfSpan = Math.floor(dim / 2);
  for (let gx = -halfSpan; gx <= halfSpan; gx++) {
    for (let gy = -halfSpan; gy <= halfSpan; gy++) {
      const isOrigin = gx === 0 && gy === 0;
      const isHit = affected.has(`${gx},${gy}`);
      const px = (gx + halfSpan) * cell;
      const py = (gy + halfSpan) * cell;
      squares.push(
        <rect
          key={`${gx}-${gy}`}
          x={px}
          y={py}
          width={cell - 1}
          height={cell - 1}
          className={
            isOrigin
              ? 'zsi-cell zsi-cell--origin'
              : isHit
              ? 'zsi-cell zsi-cell--hit'
              : 'zsi-cell zsi-cell--empty'
          }
        />
      );
    }
  }

  return (
    <svg viewBox={`0 0 ${PX} ${PX}`} className={`zsi-svg ${className}`} aria-hidden="true">
      {squares}
    </svg>
  );
}
