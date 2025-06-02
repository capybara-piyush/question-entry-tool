from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path
from django.shortcuts import render
from django.contrib import messages
from .models import Category, Question, Option, ProductType, ProductTypeEnum
from .utils import read_google_sheet, setup_data_import_logger
import pandas as pd
import logging


class OptionInline(admin.TabularInline):
    model = Option
    extra = 4
    max_num = 4


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "question_text",
        "category",
        "time_limit",
        "is_product_question",
        "product_type",
    )
    list_filter = ("category", "is_product_question", "product_type")
    search_fields = ("question_text",)
    inlines = [OptionInline]
    readonly_fields = ("question_id",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    change_list_template = "admin/category/change_list.html"
    readonly_fields = ("category_id",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("upload-excel/", self.upload_excel, name="upload-excel"),
            path("import-sheets/", self.import_sheets, name="import-sheets"),
        ]
        return custom_urls + urls

    def process_data(self, request, data_dict):
        logger, log_file = setup_data_import_logger()
        logger.info("Starting data import process")

        try:
            category_id_mapping = Category.get_category_id_mapping()

            for name, category_id in category_id_mapping.items():
                Category.objects.get_or_create(category_id=category_id, name=name)

            excel_questions = set()
            for sheet_name, df in data_dict.items():
                for index, row in df.iterrows():
                    if not (pd.isna(row[0]) or str(row[0]).strip() == ""):
                        question_text = str(row[0]).strip()
                        excel_questions.add(question_text)

            existing_questions = {}
            for category in Category.objects.all():
                questions = Question.objects.filter(category=category).prefetch_related(
                    "option_set"
                )
                for question in questions:
                    key = question.question_text.strip()
                    options = list(question.option_set.all())
                    options_data = {
                        "correct": next(
                            (opt.option_text for opt in options if opt.is_correct), None
                        ),
                        "incorrect": [
                            opt.option_text for opt in options if not opt.is_correct
                        ],
                    }
                    existing_questions[key] = {
                        "question": question,
                        "options": options_data,
                        "found_in_excel": key in excel_questions,
                    }

            questions_to_create = []
            questions_to_update = []

            for sheet_name, df in data_dict.items():
                logger.info(f"Processing sheet: {sheet_name}")

                category_id = next(
                    (
                        id
                        for name, id in category_id_mapping.items()
                        if name.lower() == sheet_name.lower()
                    ),
                    None,
                )

                if category_id is None:
                    logger.error(
                        f"Invalid sheet name: {sheet_name}. Must be one of {list(category_id_mapping.keys())}"
                    )
                    continue

                category = Category.objects.get(category_id=category_id)

                for index, row in df.iterrows():
                    row_num = index + 2
                    try:
                        if pd.isna(row[0]) or str(row[0]).strip() == "":
                            logger.error(
                                f"Sheet: {sheet_name}, Row: {row_num} - Question text is empty"
                            )
                            continue

                        if pd.isna(row[1]) or str(row[1]).strip() == "":
                            logger.error(
                                f"Sheet: {sheet_name}, Row: {row_num} - Correct answer is empty"
                            )
                            continue

                        question_text = str(row[0]).strip()
                        key = question_text

                        product_value = (
                            row.get("Product", "").strip().upper()
                            if pd.notna(row.get("Product", ""))
                            else ""
                        )
                        is_product = product_value in ["AMAZON", "GOOGLE"]
                        product_type = None

                        if is_product:
                            product_type, _ = ProductType.objects.get_or_create(
                                name=product_value, defaults={"is_active": True}
                            )
                            logger.info(
                                f"Sheet: {sheet_name}, Row: {row_num} - Valid product type: {product_value}"
                            )
                        else:
                            if product_value:
                                logger.warning(
                                    f"Sheet: {sheet_name}, Row: {row_num} - Invalid or unsupported product type: {product_value}. "
                                    f"Only AMAZON and GOOGLE are supported."
                                )
                                self.message_user(
                                    request,
                                    f"Warning: Invalid or unsupported product type '{product_value}' found in sheet '{sheet_name}', row {row_num}. "
                                    f"Only AMAZON and GOOGLE are supported. Treating as non-product question.",
                                    level="WARNING",
                                )

                        new_options = {
                            "correct": str(row[1]).strip(),
                            "incorrect": [
                                str(row[i]).strip()
                                for i in range(2, 5)
                                if pd.notna(row[i]) and str(row[i]).strip()
                            ],
                        }

                        if key in existing_questions:
                            existing_data = existing_questions[key]
                            existing_question = existing_data["question"]
                            existing_options = existing_data["options"]

                            # Only update if it's in a different category or has changes
                            if (
                                existing_question.category_id != category_id
                                or existing_question.is_product_question != is_product
                                or existing_question.product_type != product_type
                                or existing_options["correct"] != new_options["correct"]
                                or set(existing_options["incorrect"])
                                != set(new_options["incorrect"])
                            ):
                                questions_to_update.append(
                                    {
                                        "question": existing_question,
                                        "category": category,
                                        "is_product_question": is_product,
                                        "product_type": product_type,
                                        "options": new_options,
                                        "time_limit": 60 if is_product else 15,
                                        "hint": "Hint Text" if is_product else None,
                                    }
                                )
                                logger.info(
                                    f"Sheet: {sheet_name}, Row: {row_num} - Question will be updated: {existing_question.question_id}"
                                )
                        else:
                            questions_to_create.append(
                                {
                                    "category": category,
                                    "question_text": question_text,
                                    "is_product_question": is_product,
                                    "product_type": product_type,
                                    "time_limit": 60 if is_product else 15,
                                    "hint": "Hint Text" if is_product else None,
                                    "options": new_options,
                                }
                            )
                            logger.info(
                                f"Sheet: {sheet_name}, Row: {row_num} - New question will be created"
                            )

                    except Exception as row_error:
                        error_msg = f"Error processing row {row_num} in sheet '{sheet_name}': {str(row_error)}"
                        logger.error(error_msg)
                        self.message_user(request, error_msg, level="ERROR")
                        continue

            from django.db import transaction

            with transaction.atomic():
                # Only delete questions that don't exist in any sheet
                questions_to_delete = [
                    data["question"]
                    for data in existing_questions.values()
                    if not data["found_in_excel"]
                ]

                for question_data in questions_to_create:
                    options = question_data.pop("options")
                    question = Question.objects.create(**question_data)
                    Option.objects.create(
                        question=question,
                        option_text=options["correct"],
                        is_correct=True,
                    )
                    for incorrect_option in options["incorrect"]:
                        Option.objects.create(
                            question=question,
                            option_text=incorrect_option,
                            is_correct=False,
                        )
                    logger.info(f"Created new question: {question.question_id}")

                for update_data in questions_to_update:
                    question = update_data["question"]
                    options = update_data.pop("options")
                    for field, value in update_data.items():
                        setattr(question, field, value)
                    question.save()

                    question.option_set.all().delete()
                    Option.objects.create(
                        question=question,
                        option_text=options["correct"],
                        is_correct=True,
                    )
                    for incorrect_option in options["incorrect"]:
                        Option.objects.create(
                            question=question,
                            option_text=incorrect_option,
                            is_correct=False,
                        )
                    logger.info(f"Updated question: {question.question_id}")

                for question in questions_to_delete:
                    question_id = question.question_id
                    question.delete()
                    logger.info(f"Deleted question: {question_id}")

                logger.info(
                    f"Summary: Created {len(questions_to_create)} questions, Updated {len(questions_to_update)} questions, Deleted {len(questions_to_delete)} questions"
                )

            success_msg = f"Data processed successfully. Check the log file for details: {log_file}"
            logger.info("Data import completed successfully")
            self.message_user(request, success_msg)

        except Exception as e:
            error_msg = f"Error processing data: {str(e)}"
            logger.error(error_msg)
            self.message_user(request, error_msg, level="ERROR")

    def upload_excel(self, request):
        if request.method == "POST" and request.FILES.get("excel_file"):
            excel_file = request.FILES["excel_file"]
            try:
                xls = pd.ExcelFile(excel_file)
                data_dict = {}
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    data_dict[sheet_name] = df

                self.process_data(request, data_dict)
            except Exception as e:
                self.message_user(
                    request, f"Error processing Excel file: {str(e)}", level="ERROR"
                )

            return HttpResponseRedirect("../")

        return render(request, "admin/category/upload.html")

    def import_sheets(self, request):
        if request.method == "POST" and request.POST.get("sheet_url"):
            sheet_url = request.POST["sheet_url"]
            try:
                data_dict = read_google_sheet(sheet_url)
                self.process_data(request, data_dict)
            except Exception as e:
                self.message_user(
                    request,
                    f"Error importing from Google Sheets: {str(e)}",
                    level="ERROR",
                )

            return HttpResponseRedirect("../")

        return HttpResponseRedirect("../")


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("option_text", "question", "is_correct")
    list_filter = ("is_correct", "question__category")
    search_fields = ("option_text", "question__question_text")
    readonly_fields = ("option_id",)


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("product_type_id",)
