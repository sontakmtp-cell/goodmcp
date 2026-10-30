"""Bounded JSON schemas for reviewed Python adapters. No financial formulas here."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Money = Annotated[float, Field(ge=0, le=1e16, allow_inf_nan=False)]
Rate = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, le=100000, strict=True)]
Year = Annotated[int, Field(ge=1, le=100, strict=True)]
PROVINCES = ('bac_ninh','hai_phong','bac_giang','binh_duong','dong_nai','ho_chi_minh','quang_ngai','da_nang')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class CIT(Strict):
    revenue: Money
    cost: Money
    rate: Rate = 20
    free_years: Annotated[int, Field(ge=0,le=100,strict=True)] = 0
    half_years: Annotated[int, Field(ge=0,le=100,strict=True)] = 0
    loss_carry: Money | None = None
    year: Year | None = None


class Schedule(Strict):
    revenue: Money
    cost: Money
    rate: Rate = 20
    free_years: Annotated[int, Field(ge=0,le=50,strict=True)] = 0
    half_years: Annotated[int, Field(ge=0,le=50,strict=True)] = 0
    loss_carry: Money | None = None
    horizon: Year | None = None


class Payroll(Strict):
    headcount: Count
    monthly_gross_wage: Money
    dependents: Annotated[int, Field(ge=0,le=100,strict=True)] = 0


class Withhold(Strict):
    gross_payment: Money
    rate: Rate = 10


class Grossup(Strict):
    net_amount: Money
    rate: Rate = 10


class Tariff(Strict):
    cif: Annotated[float, Field(gt=0,le=1e16,allow_inf_nan=False)]
    category: Literal['machinery_import','raw_material','intermediate','finished_goods','alcohol','vehicle','tobacco']
    vat_override: Rate | None = None


class Location(Strict):
    headcount: Count
    factory_area: Money
    land_area: Money
    provinces: Annotated[list[Literal['bac_ninh','hai_phong','bac_giang','binh_duong','dong_nai','ho_chi_minh','quang_ngai','da_nang']],Field(min_length=1,max_length=8)] | None = None
    profit: Money | None = None
    cit_override: Rate | None = None


class Empty(Strict): pass


MODELS = {'cit_estimate':CIT,'cit_schedule':Schedule,'payroll_total':Payroll,'fct_withhold':Withhold,
          'fct_grossup':Grossup,'tariff':Tariff,'location_sim':Location,'refs_calendar':Empty,'refs_odi':Empty,
          }


def validate(operation, arguments):
    if operation not in MODELS: raise ValueError('Unknown approved adapter')
    return MODELS[operation].model_validate(arguments).model_dump()
