import React, { useEffect, useState } from 'react';
import spellsData from '../data/spells_clean.json';
import ZoneShapeIcon, { zoneCaption } from './ZoneShapeIcon';
import './SpellDetailsPanel.css';

const spellNameById = Object.fromEntries(spellsData.map(s => [s.id, s.nameFr]));

// ── Formatting helpers ────────────────────────────────────────────────────────

const elementColor = id => {
  switch (id) {
    case 1: return 'var(--element-earth)';
    case 2: return 'var(--element-fire)';
    case 3: return 'var(--element-water)';
    case 4: return 'var(--element-air)';
    case 0: case 5: return 'var(--element-neutral)';
    default: return 'var(--text-primary)';
  }
};

const fmtRange = r => !r ? '?' : r.min === r.max ? String(r.max) : `${r.min}–${r.max}`;
const fmtCasts = v => (v == null || v === 0) ? '∞' : String(v);
const fmtTurns = v => (!v || v === 0) ? null : `${v}t`;
const fmtStack = v => (v == null || v <= 0) ? null : String(v);
const fmtCrit = v => (v == null || v === 0) ? null : `${v}%`;

// ── Effects side-by-side helpers ──────────────────────────────────────────────

/**
 * Zip normal and crit effects by index.
 * Effects with the same textFr are first collapsed into one row with merged conditions.
 * Returns [{normal, crit, changed}]
 */
function collapseEffects(effects = []) {
  // Group consecutive effects with the same textFr into one entry,
  // merging their conditions arrays.
  const collapsed = [];
  for (const e of effects) {
    if (!e.textFr) continue;
    const prev = collapsed[collapsed.length - 1];
    if (prev && prev.textFr === e.textFr) {
      // Merge conditions — append unique ones
      const incoming = e.conditions ?? [];
      const existing = new Set((prev.conditions ?? []).map(c => c.label + c.negate));
      for (const c of incoming) {
        if (!existing.has(c.label + c.negate)) {
          prev.conditions = [...(prev.conditions ?? []), c];
          existing.add(c.label + c.negate);
        }
      }
    } else {
      collapsed.push({ ...e, conditions: e.conditions ? [...e.conditions] : [] });
    }
  }
  return collapsed;
}

function zipEffects(effects = [], critEffects = []) {
  const normCollapsed = collapseEffects(effects);
  const critCollapsed = collapseEffects(critEffects);
  const n = Math.max(normCollapsed.length, critCollapsed.length);
  const rows = [];
  for (let i = 0; i < n; i++) {
    const normal = normCollapsed[i] ?? null;
    const crit = critCollapsed[i] ?? null;
    if (!normal && !crit) continue;
    rows.push({
      normal,
      crit,
      changed: normal?.textFr !== crit?.textFr,
    });
  }
  return rows;
}

// ── Characteristic chips ──────────────────────────────────────────────────────

function buildChips(lvl) {
  if (!lvl) return [];
  const rows = [];

  // Targets first — most useful context
  if (lvl.targets) rows.push({ key: 'Cibles', val: lvl.targets, full: true });

  rows.push({ key: 'Lancers / tour', val: fmtCasts(lvl.castsPerTurn) });
  rows.push({ key: 'Lancers / cible', val: fmtCasts(lvl.castsPerTarget) });

  const crit = fmtCrit(lvl.criticalRate);
  if (crit) rows.push({ key: 'Coup critique', val: crit, accent: true });

  const cd = fmtTurns(lvl.cooldown);
  if (cd) rows.push({ key: 'Rechargement', val: cd });

  const icd = fmtTurns(lvl.initialCooldown);
  if (icd) rows.push({ key: 'Début combat', val: icd });

  const intv = fmtTurns(lvl.minCastInterval);
  if (intv) rows.push({ key: 'Intervalle min.', val: intv });

  const stk = fmtStack(lvl.stackLimit);
  if (stk) rows.push({ key: 'Cumuls max.', val: stk });

  rows.push({ key: 'Ligne de vue', val: lvl.lineOfSight ? 'Oui' : 'Non' });

  if (lvl.castInLine) rows.push({ key: 'En ligne seul.', val: 'Oui' });
  if (lvl.range?.modifiable) rows.push({ key: 'Portée modif.', val: 'Oui' });
  if (lvl.requiresFreeCell) rows.push({ key: 'Case libre req.', val: 'Oui' });

  return rows;
}

// ── UncertainLabel — renders a label, styling a trailing "†" (uncertain
// interpretation, from the label-audit pass) as its own hoverable mark ──────

const UNCERTAIN_MARK = '\u2009†';

function UncertainLabel({ text }) {
  if (!text || !text.includes(UNCERTAIN_MARK)) return text;
  const parts = text.split(UNCERTAIN_MARK).filter(Boolean);
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          <span
            className="uncertain-mark"
            title="Sens exact non confirmé — meilleure interprétation possible d'après l'analyse des données du jeu."
          >
            †
          </span>
        </span>
      ))}
    </>
  );
}

// ── AreaBadge — square-grid zone icon + compact text caption ────────────────
// Reads the raw {type, shape, size} area object directly (no backend
// change needed — geometry is computed client-side, see ZoneShapeIcon.jsx).

function AreaBadge({ area }) {
  if (!area || !area.type) return null;
  const caption = zoneCaption(area.type, area.size, area.shape);
  if (!caption) return null; // single-cell hit, nothing worth showing

  return (
    <span className="area-badge" title={`Zone : ${caption}`}>
      <ZoneShapeIcon type={area.type} shape={area.shape} size={area.size} className="area-badge-icon" />
      <span className="area-badge-text">{caption}</span>
    </span>
  );
}

// ── ConditionTags — ⓘ icon with CSS-only hover tooltip ───────────────────────

function ConditionTags({ conditions, dispellableLabel }) {
  const hasContent = (conditions && conditions.length > 0) || dispellableLabel;
  if (!hasContent) return null;

  return (
    <span className="cond-wrap">
      <span className="cond-icon" aria-label="Conditions">ⓘ</span>
      <span className="cond-tooltip" role="tooltip">
        {dispellableLabel && (
          <span className="cond-line cond-disp">⚑ {dispellableLabel}</span>
        )}
        {dispellableLabel && conditions?.length > 0 && (
          <span className="cond-divider" />
        )}
        {conditions?.length > 0 && (
          <span className="cond-tooltip-title">Conditions</span>
        )}
        {(conditions ?? []).map((c, i) => (
          <span
            key={i}
            className={`cond-line ${c.type === 'trigger' ? 'cond-trig' : c.negate ? 'cond-neg' : 'cond-pos'}`}
          >
            {c.type === 'trigger' ? <>⏱ <UncertainLabel text={c.label} /></> : c.negate ? <>✗ si non : <UncertainLabel text={c.label} /></> : <>✓ si : <UncertainLabel text={c.label} /></>}
          </span>
        ))}
      </span>
    </span>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function SpellDetailsPanel({ spell, onDeselect }) {
  const [gradeIdx, setGradeIdx] = useState(0);

  useEffect(() => { setGradeIdx(0); }, [spell?.id]);

  // ── Empty state ──
  if (!spell) {
    return (
      <div className="details-col-outer details-empty">
        <div className="details-col">
          <p>Sélectionnez un sort</p>
        </div>
      </div>
    );
  }

  const levels = spell.levels || [];
  const lvl = levels[gradeIdx] || levels[0];
  const name = spell.nameFr || 'Sort inconnu';
  const desc = spell.descriptionFr || '';
  const baseName = spell.isVariant && spell.variantOf
    ? spellNameById[spell.variantOf] ?? null
    : null;

  const effectRows = lvl ? zipEffects(
    lvl.effects ?? [],
    lvl.criticalEffects ?? []
  ) : [];

  const chips = buildChips(lvl);
  const hasCrits = (lvl?.criticalEffects ?? []).some(e => e.textFr);

  return (
    <div className="details-col-outer" role="dialog" aria-modal="true" aria-label={name}>
      <div className="details-col">

        {/* ── Close / back — visible only as an overlay on mobile ── */}
        <button
          type="button"
          className="dh-close"
          onClick={onDeselect}
          aria-label="Retour à la liste des sorts"
        >
          ← Retour
        </button>

        {/* ── Header ── */}
        <header className="dh">
          <div className="dh-icon">
            {spell.imgUrl && (
              <img
                src={spell.imgUrl}
                alt=""
                className="dh-icon-img"
                onError={e => { e.currentTarget.style.display = 'none'; }}
              />
            )}
          </div>
          <div className="dh-text">
            <div className="dh-title-row">
              <h2 className="dh-name">{name}</h2>
              {baseName && <span className="dh-variant-badge">↩ {baseName}</span>}
            </div>
            <div className="dh-meta">
              {lvl && <>
                <span className="dh-meta-tag">{lvl.pa ?? '?'} PA</span>
                <span className="dh-meta-tag">{fmtRange(lvl.range)} PO</span>
              </>}
              {levels.length > 0 && (
                <span className="dh-meta-levels">
                  Niveaux {levels.map(l => l.requiredLevel ?? '?').join(' / ')}
                </span>
              )}
            </div>
          </div>
        </header>

        {/* ── Description ── */}
        {desc && (
          <p className="dh-desc">{desc}</p>
        )}

        {/* ── Grade tabs ── */}
        {levels.length > 1 && (
          <div className="grade-tabs">
            {levels.map((l, i) => (
              <button
                key={l.id || i}
                className={`grade-tab${i === gradeIdx ? ' active' : ''}`}
                onClick={() => setGradeIdx(i)}
              >
                Rang {l.grade ?? i + 1}
              </button>
            ))}
          </div>
        )}

        {/* ── Effects side-by-side ── */}
        {lvl && (
          <div className="effects-area">

            {/* Column headers */}
            <div className="effects-header">
              <span className="eff-col-label">Effets</span>
              {hasCrits && <span className="eff-col-label crit-label">Critique</span>}
            </div>

            {effectRows.length > 0 ? (
              <ul className="effects-rows">
                {effectRows.map((row, i) => (
                  <li key={i} className="effect-row">
                    {/* Normal */}
                    <div className="eff-cell">
                      <span style={row.normal ? { color: elementColor(row.normal.elementId) } : undefined}>
                        {row.normal?.textFr ?? <span className="eff-empty">—</span>}
                      </span>
                      {row.normal?.area && <AreaBadge area={row.normal.area} />}
                      {(row.normal?.conditions?.length > 0 || row.normal?.dispellableLabel) && (
                        <ConditionTags
                          conditions={row.normal.conditions}
                          dispellableLabel={row.normal.dispellableLabel}
                        />
                      )}
                    </div>

                    {/* Crit — only render column if any crits exist */}
                    {hasCrits && (
                      <div className={`eff-cell crit-cell${row.changed ? ' changed' : ''}`}>
                        <span style={row.crit ? { color: elementColor(row.crit.elementId) } : undefined}>
                          {row.crit?.textFr ?? <span className="eff-empty">—</span>}
                        </span>
                        {row.crit?.area && <AreaBadge area={row.crit.area} />}
                        {(row.crit?.conditions?.length > 0 || row.crit?.dispellableLabel) && (
                          <ConditionTags
                            conditions={row.crit.conditions}
                            dispellableLabel={row.crit.dispellableLabel}
                          />
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="eff-none">Aucun effet</p>
            )}
          </div>
        )}

        {/* ── Characteristics ── */}
        {chips.length > 0 && (
          <div className="chars-area">
            <span className="chars-label">Caractéristiques</span>
            <div className="chars-grid">
              {chips.map((c, i) => (
                <div key={i} className={`char-row${c.accent ? ' char-accent' : ''}${c.full ? ' char-full' : ''}`}>
                  <span className="char-key">{c.key}</span>
                  <strong className="char-val"><UncertainLabel text={c.val} /></strong>
                </div>
              ))}
            </div>
            {chips.some(c => c.val?.includes(UNCERTAIN_MARK)) && (
              <p className="uncertain-legend">
                <span className="uncertain-mark">†</span> sens non confirmé — meilleure interprétation
              </p>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
