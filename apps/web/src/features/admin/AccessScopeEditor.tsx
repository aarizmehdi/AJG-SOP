import type { AccessScope } from '../../types/policy';
import { CatalogMultiSelect } from '../system-admin/CatalogMultiSelect';
import { useOrganizationCatalogs } from '../system-admin/catalogs';

type Dimension = keyof AccessScope;
const labels: Record<Dimension, string> = {
  departments: 'departments',
  locations: 'locations',
  roles: 'organizational roles',
};

export function AccessScopeEditor({
  value,
  onChange,
}: {
  value: AccessScope;
  onChange: (scope: AccessScope) => void;
}) {
  const catalogs = useOrganizationCatalogs(true);
  const update = (
    dimension: Dimension,
    mode: 'all' | 'selected',
    values?: string[],
  ) => {
    onChange({
      ...value,
      [dimension]: {
        mode,
        values: mode === 'all' ? [] : (values ?? value[dimension].values),
      },
    });
  };
  return (
    <fieldset className="scope-editor">
      <legend>Employee access</legend>
      <p>
        Access is OR within each dimension and AND across all three dimensions.
      </p>
      {(Object.keys(labels) as Dimension[]).map((dimension) => (
        <div className="scope-row" key={dimension}>
          <strong>{labels[dimension]}</strong>
          <label>
            <input
              type="radio"
              name={`${dimension}-mode`}
              checked={value[dimension].mode === 'all'}
              onChange={() => {
                update(dimension, 'all');
              }}
            />
            All {labels[dimension]}
          </label>
          <label>
            <input
              type="radio"
              name={`${dimension}-mode`}
              checked={value[dimension].mode === 'selected'}
              onChange={() => {
                update(dimension, 'selected', ['']);
              }}
            />
            Selected {labels[dimension]}
          </label>
          {value[dimension].mode === 'selected' && (
            <CatalogMultiSelect
              label={`Selected ${labels[dimension]}`}
              items={
                catalogs.data?.[
                  dimension === 'roles' ? 'organizational_roles' : dimension
                ] ?? []
              }
              value={value[dimension].values}
              disabled={catalogs.isPending || catalogs.isError}
              onChange={(values) => {
                update(dimension, 'selected', values);
              }}
            />
          )}
        </div>
      ))}
      {catalogs.isPending && (
        <small role="status">Loading organization access options…</small>
      )}
      {catalogs.isError && (
        <small className="form-error" role="alert">
          Organization access options could not be loaded.
        </small>
      )}
      <small>
        “Selected” must contain at least one value. An empty selection is never
        unrestricted.
      </small>
    </fieldset>
  );
}
