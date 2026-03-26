from pydantic import BaseModel, ConfigDict


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company: str
    role: str
    period: str
    description: str


class SkillCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    skills: list[str]


class EducationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    institution: str
    degree: str
    period: str
    note: str | None


class AboutOut(BaseModel):
    experience: list[ExperienceOut]
    skills: list[SkillCategoryOut]
    education: list[EducationOut]
