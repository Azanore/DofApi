import React, { useState, useMemo, useEffect } from 'react';
import './App.css';
import Sidebar from './components/Sidebar';
import SpellGrid from './components/SpellGrid';
import SpellDetailsPanel from './components/SpellDetailsPanel';
import spellsData from './data/spells_clean.json';

function App() {
  const [selectedClass, setSelectedClass] = useState(null);
  const [selectedSpell, setSelectedSpell] = useState(null);

  const classes = useMemo(() => {
    const classMap = new Map();
    spellsData.forEach(s => {
      if (s.class && s.class.breedId && !classMap.has(s.class.breedId)) {
        classMap.set(s.class.breedId, s.class);
      }
    });
    return Array.from(classMap.values()).sort((a, b) => a.breedId - b.breedId);
  }, []);

  useEffect(() => {
    if (classes.length > 0 && !selectedClass) {
      setSelectedClass(classes[0]);
    }
  }, [classes, selectedClass]);

  // Pairs: [[base, variant], [base, variant], …]  (22 pairs × 2 = 44)
  const spellPairs = useMemo(() => {
    if (!selectedClass) return [];
    const all = spellsData.filter(s => s.class?.breedId === selectedClass.breedId);
    const bases = all.filter(s => !s.isVariant);
    return bases.map(base => {
      const variant = all.find(s => s.variantOf === base.id) ?? null;
      return [base, variant];
    });
  }, [selectedClass]);

  return (
    <div className="app-container">
      {/* Col 1 — class picker */}
      <Sidebar
        classes={classes}
        selectedClass={selectedClass}
        onSelectClass={cls => {
          if (selectedClass?.breedId !== cls.breedId) {
            setSelectedClass(cls);
            setSelectedSpell(null);
          }
          // clicking the active class does nothing — it's a tab, not a toggle
        }}
      />

      {/* Col 2 — spell grid */}
      <SpellGrid
        pairs={spellPairs}
        selectedSpellId={selectedSpell?.id}
        onSelectSpell={spell => {
          // clicking selected spell deselects it
          setSelectedSpell(prev => prev?.id === spell.id ? null : spell);
        }}
        className={selectedClass?.nameFr}
      />

      {/* Col 3 — details (always present) */}
      <SpellDetailsPanel
        spell={selectedSpell}
        onDeselect={() => setSelectedSpell(null)}
      />
    </div>
  );
}

export default App;
