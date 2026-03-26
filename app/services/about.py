from sqlalchemy.orm import Session

from app.models.about import EducationItem, ExperienceItem, SkillCategory
from app.schemas.about import AboutOut, EducationOut, ExperienceOut, SkillCategoryOut


def get_about(db: Session) -> AboutOut:
    experience = (
        db.query(ExperienceItem).order_by(ExperienceItem.sort_order).all()
    )
    skills = db.query(SkillCategory).order_by(SkillCategory.sort_order).all()
    education = db.query(EducationItem).order_by(EducationItem.sort_order).all()

    return AboutOut(
        experience=[ExperienceOut.model_validate(e) for e in experience],
        skills=[SkillCategoryOut.model_validate(s) for s in skills],
        education=[EducationOut.model_validate(e) for e in education],
    )
