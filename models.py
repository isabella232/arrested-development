import re

from peewee import *

db = SqliteDatabase('data/app.db')


def slugify(text):
    value = re.sub('[^\w\s-]', '', text).strip().lower()
    return re.sub('[^\w\s-]', '', value).strip().lower()


class Joke(Model):
    primary_character = TextField()
    code = IntegerField()
    text = TextField()

    class Meta:
        database = db

    @classmethod
    def slug():
        return slugify(self.text)


class Episode(Model):
    season = IntegerField()
    episode = IntegerField()
    code = TextField()
    title = TextField()

    rating = TextField(null=True)
    directed_by = TextField(null=True)
    written_by = TextField(null=True)
    production_code = CharField(max_length=255, null=True)
    run_date = DateField(null=True)

    wikipedia_link = TextField(null=True)
    netflix_link = TextField(null=True)

    class Meta:
        database = db

    @classmethod
    def slug():
        return slugify(self.code)


class EpisodeJoke(Model):
    joke = ForeignKeyField(Joke, cascade=False)
    episode = ForeignKeyField(Episode, cascade=False)
    joke_type = CharField(length=1, help_text="Choices are: f, b or 1")
    code = TextField()

    details = TextField(null=True)
    origin = TextField(null=True)
    connection = TextField(null=True)

    class Meta:
        database = db

    def extras(self):
        payload = ''

        for attribute in ['Details', 'Origin', 'Connection']:
            if getattr(self, attribute.lower()):
                payload += '<span class="extra"><strong>%s</strong>: %s</span>' % (attribute, getattr(self, attribute.lower()))

        return payload

    @classmethod
    def slug():
        return slugify(self.code)
