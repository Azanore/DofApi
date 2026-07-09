import React from 'react';
import SpellCard from './SpellCard';
import './SpellGrid.css';

/**
 * SpellGrid — 11 rows × 4 spells (2 pairs per row).
 *
 * `pairs` is an array of [base, variant] tuples (22 pairs = 44 spells).
 * We group pairs into rows of 2: [[pair0, pair1], [pair2, pair3], …]
 * Within a row: base₀ · variant₀ ·· gap ·· base₁ · variant₁
 */
export default function SpellGrid({ pairs, selectedSpellId, onSelectSpell, className }) {
  if (!pairs || pairs.length === 0) {
    return (
      <div className="spell-grid-col">
        <div className="spell-grid-empty">
          <p>Sélectionnez une classe</p>
        </div>
      </div>
    );
  }

  // Group 22 pairs into 11 rows of 2 pairs each
  const rows = [];
  for (let i = 0; i < pairs.length; i += 2) {
    rows.push([pairs[i], pairs[i + 1] ?? [null, null]]);
  }

  return (
    <div className="spell-grid-col">
      {/* Compact class label at the top */}
      <div className="spell-grid-label">{className ?? ''}</div>

      <div className="spell-grid">
        {rows.map((row, rowIdx) => (
          <div key={rowIdx} className="spell-row">
            {row.map(([base, variant], pairIdx) => (
              <div key={pairIdx} className="spell-pair">
                <SpellCard
                  spell={base}
                  selectedSpellId={selectedSpellId}
                  onSelectSpell={onSelectSpell}
                />
                <SpellCard
                  spell={variant}
                  selectedSpellId={selectedSpellId}
                  onSelectSpell={onSelectSpell}
                  isVariantSlot
                />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
