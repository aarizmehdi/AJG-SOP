import { Check, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { CatalogItem } from '../../types/admin';

export function CatalogMultiSelect({
  label,
  items,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  items: CatalogItem[];
  value: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
}) {
  const [search, setSearch] = useState('');
  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return items.filter(
      (item) =>
        !needle ||
        item.name.toLocaleLowerCase().includes(needle) ||
        item.key.toLocaleLowerCase().includes(needle),
    );
  }, [items, search]);
  const toggle = (key: string) => {
    onChange(
      value.includes(key)
        ? value.filter((current) => current !== key)
        : [...value, key],
    );
  };
  return (
    <fieldset className="catalog-select" disabled={disabled}>
      <legend>{label}</legend>
      {items.length > 6 && (
        <label className="catalog-select-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Search {label}</span>
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
            placeholder={`Search ${label.toLowerCase()}`}
          />
        </label>
      )}
      <div className="catalog-options">
        {visible.map((item) => {
          const selected = value.includes(item.key);
          return (
            <label
              key={item.id}
              className={`catalog-option${selected ? ' selected' : ''}${!item.active ? ' inactive' : ''}`}
            >
              <input
                type="checkbox"
                aria-label={item.name}
                checked={selected}
                disabled={!item.active && !selected}
                onChange={() => {
                  toggle(item.key);
                }}
              />
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.active ? item.key : `${item.key} · Inactive`}
                </small>
              </span>
              {selected && <Check size={16} aria-hidden="true" />}
            </label>
          );
        })}
      </div>
      {!visible.length && <p className="field-help">No matching options.</p>}
    </fieldset>
  );
}
