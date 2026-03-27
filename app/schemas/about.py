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


class SocialLinkOut(BaseModel):
    platform: str
    url: str


class ProfileOut(BaseModel):
    tagline: str
    short_bio: str
    long_bio: list[str]
    social_links: list[SocialLinkOut]


class ProfileUpdate(BaseModel):
    tagline: str | None = None
    short_bio: str | None = None
    long_bio: list[str] | None = None
    social_links: list[SocialLinkOut] | None = None


class AboutOut(BaseModel):
    profile: ProfileOut
    experience: list[ExperienceOut]
    skills: list[SkillCategoryOut]
    education: list[EducationOut]


class AboutUpdate(BaseModel):
    experience: list[ExperienceOut] | None = None
    skills: list[SkillCategoryOut] | None = None
    education: list[EducationOut] | None = None
