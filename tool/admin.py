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
            for sheet_name, df in data_dict.items():
                logger.info(f"Processing sheet: {sheet_name}")
                category, _ = Category.objects.get_or_create(name=sheet_name)

                for index, row in df.iterrows():
                    row_num = index + 2
                    try:
                        logger.info(f"Processing row {row_num} in sheet {sheet_name}")

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

                        question = Question.objects.create(
                            category=category,
                            question_text=row[0],
                            is_product_question=is_product,
                            product_type=product_type,
                        )
                        logger.info(
                            f"Sheet: {sheet_name}, Row: {row_num} - Created question: {question.question_id}"
                        )

                        Option.objects.create(
                            question=question, option_text=row[1], is_correct=True
                        )

                        for i in range(2, 5):
                            if pd.notna(row[i]) and str(row[i]).strip():
                                Option.objects.create(
                                    question=question,
                                    option_text=row[i],
                                    is_correct=False,
                                )
                            else:
                                logger.warning(
                                    f"Sheet: {sheet_name}, Row: {row_num} - Missing option for column {i + 1}"
                                )

                    except Exception as row_error:
                        error_msg = f"Error processing row {row_num} in sheet '{sheet_name}': {str(row_error)}"
                        logger.error(error_msg)
                        self.message_user(request, error_msg, level="ERROR")
                        continue

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
