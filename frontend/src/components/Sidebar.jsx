import React from 'react';
import './Sidebar.css';

const CLASS_COLORS = {
  1: '#4fc3f7',
  2: '#a5d6a7',
  3: '#ffe082',
  4: '#ef9a9a',
  5: '#ce93d8',
  6: '#80cbc4',
  7: '#f48fb1',
  8: '#ff8a65',
  9: '#81d4fa',
  10: '#a5d6a7',
  11: '#ef5350',
  12: '#80cbc4',
  13: '#b0bec5',
  14: '#ffcc02',
  15: '#90caf9',
  16: '#80deea',
  17: '#e1bee7',
  18: '#bcaaa4',
  20: '#ffab40',
};

export default function Sidebar({ classes, selectedClass, onSelectClass }) {
  return (
    <aside className="sidebar">
      <div className="class-grid">
        {classes.map(cls => {
          const name = cls.nameFr || `Classe ${cls.breedId}`;
          const active = selectedClass?.breedId === cls.breedId;
          const color = CLASS_COLORS[cls.breedId] || '#00e5ff';

          return (
            <button
              key={cls.breedId}
              className={`class-btn${active ? ' active' : ''}`}
              style={{ '--class-color': color }}
              onClick={() => onSelectClass(cls)}
              title={name}
              aria-label={name}
              aria-pressed={active}
            >
              <img
                src={cls.imgUrl}
                alt={name}
                className="class-img"
                onError={e => {
                  e.currentTarget.style.display = 'none';
                  e.currentTarget.nextSibling.style.display = 'flex';
                }}
              />
              {/* Fallback letter avatar */}
              <span
                className="class-fallback"
                style={{ display: 'none', background: color }}
              >
                {name.charAt(0)}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
