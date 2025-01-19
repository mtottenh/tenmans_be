from pydantic import BaseModel, UUID4, ConfigDict, Field, validator
from typing import Dict, List, Optional
from datetime import datetime

class StatusChangeRequest(BaseModel):
    """Request schema for status changes"""
    new_status: str
    reason: str = Field(..., min_length=3)
    entity_metadata: Optional[Dict] = None
    end_date: Optional[datetime] = None  # For suspensions
    
    @validator('reason')
    def validate_reason(cls, v):
        if not v.strip():
            raise ValueError("Reason cannot be empty")
        return v.strip()
    
    @validator('new_status')
    def validate_status(cls, v):
        if not v.strip().upper():
            raise ValueError("Status cannot be empty")
        return v.strip().upper()

class StatusHistoryEntry(BaseModel):
    """Schema for status history entries"""
    previous_status: Optional[str]
    new_status: str
    reason: str
    changed_by: UUID4
    created_at: datetime
    entity_metadata: Optional[Dict] = None
    
    model_config = ConfigDict(from_attributes=True)

class StatusChangeResponse(BaseModel):
    """Response schema for status changes"""
    entity_id: UUID4
    previous_status: str
    new_status: str
    reason: str
    changed_by: UUID4
    changed_at: datetime
    entity_metadata: Optional[Dict] = None
    
    model_config = ConfigDict(from_attributes=True)

class StatusHistoryResponse(BaseModel):
    """Response schema for status history"""
    entity_id: UUID4
    current_status: str
    history: List[StatusHistoryEntry]
    
    model_config = ConfigDict(from_attributes=True)

class StatusValidationError(BaseModel):
    """Error response for invalid status transitions"""
    error_type: str
    message: str
    details: Optional[Dict] = None