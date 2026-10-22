/**
 * Team 4 record ids and references to ids owned by other teams.
 * These are different types: a Team 4 id is a branded string, and an external
 * reference is an opaque id plus the owning team. Neither is a foreign key.
 */

declare const team4EntityBrand: unique symbol;
declare const externalIdBrand: unique symbol;

/** Identifier of a record this repository owns. */
export type Team4EntityId = string & { readonly [team4EntityBrand]: 'team4' };

/** Opaque identifier owned outside Team 4. */
export type OwnedId<Owner extends string> = string & { readonly [externalIdBrand]: Owner };

/** Canonical reference to a record owned outside Team 4. */
export type ExternalRef<Owner extends string = string> = {
  readonly owner: Owner;
  readonly id: OwnedId<Owner>;
};

export function asTeam4EntityId(id: string): Team4EntityId {
  return id as Team4EntityId;
}

export function asExternalRef<Owner extends string>(owner: Owner, id: string): ExternalRef<Owner> {
  return { owner, id: id as OwnedId<Owner> };
}
