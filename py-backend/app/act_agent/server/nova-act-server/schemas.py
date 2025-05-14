# schemas.py
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field

class BoolSchema(BaseModel):
    value: bool

class ProductSchema(BaseModel):
    title: str = Field(..., description="Product title or name")
    price: str = Field(..., description="Product price with currency symbol")
    rating: Optional[str] = Field(None, description="Product rating (e.g. 4.5/5)")
    available: Optional[bool] = Field(None, description="Whether the product is available/in stock")
    description: Optional[str] = Field(None, description="Brief product description")

class SearchResultItem(BaseModel):
    title: str = Field(..., description="Result title")
    url: Optional[str] = Field(None, description="Result URL")
    snippet: Optional[str] = Field(None, description="Result snippet or description")

class SearchResultSchema(BaseModel):
    results: List[SearchResultItem] = Field(..., description="List of search results")
    total_count: Optional[int] = Field(None, description="Total number of results")

class FormFieldOption(BaseModel):
    name: str = Field(..., description="Option name")
    value: Optional[str] = Field(None, description="Option value")

class FormField(BaseModel):
    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field type (text, select, checkbox, radio, date, file, password, other)")
    required: Optional[bool] = Field(False, description="Whether the field is required")
    options: Optional[List[FormFieldOption]] = Field(None, description="Options for select, radio, checkbox fields")

class FormFieldsSchema(BaseModel):
    fields: List[FormField] = Field(..., description="List of form fields")

class NavigationLink(BaseModel):
    text: str = Field(..., description="Link text")
    url: Optional[str] = Field(None, description="Link URL")

class NavigationSchema(BaseModel):
    current_url: str = Field(..., description="Current page URL")
    page_title: str = Field(..., description="Current page title")
    navigation_links: Optional[List[NavigationLink]] = Field(None, description="Navigation links on the page")
