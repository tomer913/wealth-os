# Skill: Management Page Pattern

Use this when building any CRUD management screen (Assets, Transactions, Valuations, etc.)

## Pattern overview
Every management page follows the same structure:
1. Table with rich rows (name + sub-label, type badge, status badge, action buttons)
2. Add/Edit modal (shared `Modal` component)
3. Delete confirmation (shared `ConfirmDialog` component)
4. JSON import (paste JSON → auto-fill known fields, unknown fields → metadata pairs)
5. Metadata editor (dynamic key-value pairs for `extra_data` JSONB field)

## Shared components (already built, reuse them)
```
client/src/components/shared/
├── Modal.tsx        # Modal, ConfirmDialog
├── Form.tsx         # Field, Input, Select, Textarea, FormGrid, FormSection, Divider
└── MetadataEditor.tsx  # MetadataEditor, MetaPair, pairsToJson, jsonToPairs
```

## Page template
```typescript
// 1. Imports
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { MetadataEditor, jsonToPairs, pairsToJson } from '../components/shared/MetadataEditor'
import { Field, Input, Select, FormGrid, FormSection, Divider } from '../components/shared/Form'

// 2. Query + mutations
const { data = [], isLoading } = useQuery({ queryKey: ['resource'], queryFn: getResource })
const createMut = useMutation({ mutationFn: createResource, onSuccess: () => { qc.invalidateQueries(...); closeModal() } })
const updateMut = useMutation({ mutationFn: ({ id, payload }) => updateResource(id, payload), onSuccess: ... })
const deleteMut = useMutation({ mutationFn: deleteResource, onSuccess: ... })

// 3. State
const [modalOpen, setModalOpen] = useState(false)
const [editTarget, setEditTarget] = useState<ResourceType | null>(null)
const [form, setForm] = useState(emptyForm())
const [metaPairs, setMetaPairs] = useState<MetaPair[]>([])
const [deleteTarget, setDeleteTarget] = useState<ResourceType | null>(null)
const [deleteError, setDeleteError] = useState('')
```

## Backend enriched list endpoint pattern
When a list endpoint needs counts of related objects (e.g. accounts + asset count):
```python
# Single query with LEFT JOIN — never N+1
q = (
    select(ParentModel, func.count(ChildModel.id).label("child_count"))
    .outerjoin(ChildModel, ChildModel.parent_id == ParentModel.id)
    .group_by(ParentModel.id)
)
result = await db.execute(q)
rows = result.all()
for parent, count in rows:
    parent.child_count = count  # attach computed value
return parents
```

Schema extension:
```python
class ParentReadWithCount(ParentRead):
    child_count: int = 0
```

## Delete protection pattern (backend)
```python
@router.delete("/{id}", status_code=204)
async def delete_item(id: UUID, db: AsyncSession = Depends(get_db)):
    count_q = select(func.count(ChildModel.id)).where(ChildModel.parent_id == id)
    count = (await db.execute(count_q)).scalar_one()
    if count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete — {count} linked records exist"
        )
    await db.delete(item)
```

## Key gotchas
- All FastAPI endpoints need trailing slash in frontend calls: `/api/v1/accounts/` not `/api/v1/accounts`
- Never name a Pydantic field `metadata` — collides with SQLAlchemy's MetaData class. Use `extra_data`.
- `updateAccount` uses PATCH not PUT
- Mutation pattern: `{ id, payload }` object, not spread: `mutationFn: ({ id, payload }) => updateResource(id, payload)`
- Always explicitly type onChange handlers: `(e: React.ChangeEvent<HTMLInputElement>) => ...`
- Delete error comes from: `err?.response?.data?.detail`
