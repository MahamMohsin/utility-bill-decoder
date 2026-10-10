"""Strict official output and separate non-identifying evidence models."""
from datetime import date
import math
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator

Number = int | float
class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Charge(StrictModel):
    type: Literal['energy','fixed','fpa','quarterly_adjustment','surcharge','meter_rent','subsidy','other']
    amount: Number
    @field_validator('amount')
    @classmethod
    def finite_nonzero(cls, value):
        if isinstance(value, bool) or not math.isfinite(value) or value == 0:
            raise ValueError('Amount must be a finite nonzero number')
        return value

class Tax(Charge):
    type: Literal['gst','electricity_duty','income_tax','municipal_tax','other_tax']

class Bill(StrictModel):
    provider: Literal['KE','LESCO','IESCO'] | None
    tariff: str | None
    sanctioned_load_kw: Number | None
    bill_month: str | None
    reading_date: str | None
    issue_date: str | None
    due_date: str | None
    previous_reading: Number | None
    current_reading: Number | None
    units_consumed: Number | None
    charges: list[Charge]
    total_charges: Number | None
    taxes: list[Tax]
    total_taxes: Number | None
    current_bill: Number | None
    arrears: Number | None
    payable_within_due_date: Number | None
    payable_after_due_date: Number | None
    @field_validator('reading_date','issue_date','due_date')
    @classmethod
    def dates(cls, value):
        if value is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('Expected YYYY-MM-DD')
            date.fromisoformat(value)
        return value
    @field_validator('bill_month')
    @classmethod
    def month(cls, value):
        if value is not None:
            if not re.fullmatch(r'\d{4}-\d{2}', value):
                raise ValueError('Expected YYYY-MM')
            date.fromisoformat(value+'-01')
        return value
    @field_validator('sanctioned_load_kw','previous_reading','current_reading','units_consumed',
                     'total_charges','total_taxes','current_bill','arrears',
                     'payable_within_due_date','payable_after_due_date')
    @classmethod
    def finite(cls, value):
        if value is not None and (isinstance(value,bool) or not math.isfinite(value)):
            raise ValueError('Expected finite JSON number')
        return value
    @field_validator('charges')
    @classmethod
    def subsidies(cls, value):
        if any(x.type == 'subsidy' and x.amount > 0 for x in value):
            raise ValueError('Subsidies must be negative')
        return value

class History(StrictModel):
    month: str
    units: Number | None
    bill_amount: Number | None
    payment: Number | None
    @field_validator('month')
    @classmethod
    def normalize_printed_month(cls,value):
        # Bills print compact labels such as Sep25; normalize without inventing a year.
        names = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                 'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
        match=re.fullmatch(r'([A-Za-z]{3})[\s/-]*(\d{2}|\d{4})',value.strip())
        if match and match[1].lower() in names:
            year=int(match[2])
            if year<100:
                year+=2000
            return f'{year:04d}-{names[match[1].lower()]:02d}'
        match=re.fullmatch(r'(\d{1,2})/(\d{2}|\d{4})',value.strip())
        if match and 1<=int(match[1])<=12:
            year=int(match[2])
            if year<100:
                year+=2000
            return f'{year:04d}-{int(match[1]):02d}'
        return value

class NumericFact(StrictModel):
    label: str
    value: Number
    unit: str

class LatePaymentTier(StrictModel):
    period: str
    payable_amount: Number | None
    surcharge_amount: Number | None
    surcharge_percent: Number | None

class Evidence(StrictModel):
    history: list[History]
    details: list[str]
    uncertainties: list[str]
    facts: list[NumericFact] = []
    late_payment_tiers: list[LatePaymentTier] = []
    @field_validator('history')
    @classmethod
    def combine_usage_and_payment_rows(cls,rows):
        merged={}
        for row in rows:
            if row.month not in merged:
                merged[row.month]=row
            else:
                old=merged[row.month]
                updates={name:getattr(row,name) for name in ('units','bill_amount','payment')
                         if getattr(old,name) is None and getattr(row,name) is not None}
                merged[row.month]=old.model_copy(update=updates)
        return [merged[key] for key in sorted(merged)]

class Extraction(StrictModel):
    bill: Bill
    evidence: Evidence
