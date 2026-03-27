from sqlalchemy.orm import Session

from app.models.about import EducationItem, ExperienceItem, SkillCategory
from app.models.profile import Profile
from app.schemas.about import (
    AboutOut,
    AboutUpdate,
    EducationOut,
    ExperienceOut,
    ProfileOut,
    ProfileUpdate,
    SkillCategoryOut,
    SocialLinkOut,
)


def _get_or_create_profile(db: Session) -> Profile:
    profile = db.query(Profile).first()
    if not profile:
        profile = Profile(
            id=1,
            tagline="Creative developer crafting digital experiences",
            short_bio="Software engineer building products at the intersection of code and design. Based in Berlin.",
            long_bio=[
                "Software engineer with a passion for building elegant, performant web applications. I care deeply about user experience, clean architecture, and shipping products that make a difference.",
                "Currently focused on full-stack development with TypeScript, React, and Node.js. Previously worked across fintech, e-commerce, and developer tooling. When I'm not coding, you'll find me exploring design systems, reading about distributed systems, or hiking.",
            ],
            social_links=[
                {"platform": "github", "url": "https://github.com"},
                {"platform": "linkedin", "url": "https://linkedin.com"},
                {"platform": "x", "url": "https://x.com"},
                {"platform": "email", "url": "mailto:hello@example.com"},
            ],
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _profile_to_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        tagline=profile.tagline,
        short_bio=profile.short_bio,
        long_bio=profile.long_bio,
        social_links=[SocialLinkOut(**sl) for sl in profile.social_links],
    )


def get_profile(db: Session) -> ProfileOut:
    return _profile_to_out(_get_or_create_profile(db))


def update_profile(db: Session, data: ProfileUpdate) -> ProfileOut:
    profile = _get_or_create_profile(db)

    if data.tagline is not None:
        profile.tagline = data.tagline
    if data.short_bio is not None:
        profile.short_bio = data.short_bio
    if data.long_bio is not None:
        profile.long_bio = data.long_bio
    if data.social_links is not None:
        profile.social_links = [sl.model_dump() for sl in data.social_links]

    db.commit()
    db.refresh(profile)
    return _profile_to_out(profile)


def get_about(db: Session) -> AboutOut:
    profile = _get_or_create_profile(db)
    experience = db.query(ExperienceItem).order_by(ExperienceItem.sort_order).all()
    skills = db.query(SkillCategory).order_by(SkillCategory.sort_order).all()
    education = db.query(EducationItem).order_by(EducationItem.sort_order).all()

    return AboutOut(
        profile=_profile_to_out(profile),
        experience=[ExperienceOut.model_validate(e) for e in experience],
        skills=[SkillCategoryOut.model_validate(s) for s in skills],
        education=[EducationOut.model_validate(e) for e in education],
    )


def update_about(db: Session, data: AboutUpdate) -> AboutOut:
    if data.experience is not None:
        db.query(ExperienceItem).delete()
        for i, e in enumerate(data.experience):
            db.add(ExperienceItem(
                company=e.company, role=e.role, period=e.period,
                description=e.description, sort_order=i,
            ))

    if data.skills is not None:
        db.query(SkillCategory).delete()
        for i, s in enumerate(data.skills):
            db.add(SkillCategory(title=s.title, skills=s.skills, sort_order=i))

    if data.education is not None:
        db.query(EducationItem).delete()
        for i, e in enumerate(data.education):
            db.add(EducationItem(
                institution=e.institution, degree=e.degree,
                period=e.period, note=e.note, sort_order=i,
            ))

    db.commit()
    return get_about(db)
