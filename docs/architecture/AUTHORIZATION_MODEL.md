# Authorization model

Firebase ID tokens are validated by the backend with the Firebase Admin SDK. The verified UID must exactly match one pre-provisioned, active MongoDB employee profile. That profile supplies the organization and roles. Firebase claims and client-supplied organization or scope fields are never trusted.

An access dimension is explicitly either `all` or `selected`. A selected dimension must contain at least one value. A person matches when any assigned value matches within a dimension. Department, location, and organizational-role dimensions must all pass.

```text
(department A OR department B)
AND (location A OR location B)
AND (role A OR role B)
```

SOP administrators may create or manage only scopes contained by all three assigned management dimensions. System administrators can manage unrestricted scopes. Employee searches, canonical readers, conversations, source responses, audit events, Mongo records, and Pinecone metadata are tenant-bound.

Employees normally receive authorized canonical sections. An original source is returned only when every canonical section associated with that source is authorized for the employee. Unknown and unauthorized originals both return `404` to avoid disclosure.
