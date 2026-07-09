import React from 'react';
import './SpellCard.css';

/**
 * SpellCard — a single spell tile.
 * `isVariantSlot` is true when this card occupies the variant position in a pair.
 * A null `spell` in a variant slot renders an empty placeholder.
 */
export default function SpellCard({ spell, onSelectSpell, selectedSpellId, isVariantSlot = false }) {
  // Empty variant slot — render a ghost tile to keep grid alignment
  if (!spell) {
    return <div className={`spell-tile ghost${isVariantSlot ? ' variant-slot' : ''}`} />;
  }

  const isSelected = spell.id === selectedSpellId;
  const name = spell.nameFr || 'Sort inconnu';
  const ap = spell.levels?.[0]?.pa ?? '?';

  return (
    <button
      type="button"
      className={`spell-tile${isSelected ? ' selected' : ''}${isVariantSlot ? ' variant-slot' : ''}`}
      onClick={() => onSelectSpell(spell)}
      title={`${name} (${ap} PA)${spell.isVariant ? ' — Variante' : ''}`}
      aria-label={`${name}, ${ap} PA${spell.isVariant ? ', variante' : ''}`}
      aria-pressed={isSelected}
    >
      {spell.imgUrl ? (
        <img
          src={spell.imgUrl}
          alt=""
          className="spell-icon-img"
          loading="lazy"
          onError={e => {
            e.currentTarget.style.display = 'none';
            e.currentTarget.nextSibling.style.display = 'flex';
          }}
        />
      ) : null}
      <span
        className="spell-abbr"
        style={{ display: spell.imgUrl ? 'none' : 'flex' }}
      >
        {name.substring(0, 2).toUpperCase()}
      </span>
    </button>
  );
}
