from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_secret_key: str = "change-this"
    admin_username: str = "admin"
    admin_password: str = "change-me"
    database_url: str = "sqlite:///./data/app.db"
    banner_registration_url: str = "https://bannservices.seu.edu.sa/StudentRegistrationSsb/ssb/registration"
    banner_transcript_url: str = "https://bannservices.seu.edu.sa/StudentSelfService/ssb/academicTranscript#!/UG/WEB/maintenance"
    seu_programs_url: str = "https://seu.edu.sa/ar/programs/"
    allow_final_registration: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
