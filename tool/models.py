from django.db import models
from django.utils import timezone
import uuid

# Create your models here.


class ProductTypeEnum(models.TextChoices):
    AMAZON = "AMAZON", "Amazon"
    GOOGLE = "GOOGLE", "Google"


class Category(models.Model):
    category_id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=50)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "categories"

    def __str__(self):
        return self.name

    @classmethod
    def get_category_id_mapping(cls):
        return {
            "Tech & Gadgets": 52,
            "Gaming": 53,
            "Pop Culture & Entertainment": 54,
            "Sports": 55,
            "Travel": 56,
        }


class ProductType(models.Model):
    product_type_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True, choices=ProductTypeEnum.choices)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "product_types"

    def __str__(self):
        return self.name


class Question(models.Model):
    question_id = models.AutoField(primary_key=True)
    category = models.ForeignKey(
        Category, db_column="category_id", on_delete=models.CASCADE
    )
    question_text = models.TextField()
    time_limit = models.IntegerField(default=15)
    is_product_question = models.BooleanField(default=False)
    product_type = models.ForeignKey(
        ProductType,
        db_column="product_type_id",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    hint = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "questions"

    def __str__(self):
        return self.question_text[:50]


class Option(models.Model):
    option_id = models.AutoField(primary_key=True)
    question = models.ForeignKey(
        Question, db_column="question_id", on_delete=models.CASCADE
    )
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        db_table = "options"

    def __str__(self):
        return (
            f"{self.option_text[:30]} - {'Correct' if self.is_correct else 'Incorrect'}"
        )
