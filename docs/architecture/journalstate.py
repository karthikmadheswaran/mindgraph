

class JournalState(TypedDict):
    user_id: str
    raw_text: str
    cleaned_text: str
    auto_title: str
    summary: str
    input_type: str
    attachment_url: str
    classifier: list
    core_entities: List(CoreEntity)
    deadline: List(Deadline) 
    trigger_check: bool
    dedup_check: bool 

class Deadline(TypedDict):
    description: str
    due_at: datetime
    raw_text: str
    
class CoreEntity(TypedDict):
    user_id: str
    name: str
    type: Entitytype

