"""
Generator tools — produce ready-to-copy markup from form data.
Phase B: Schema Markup, robots.txt, XML Sitemap, Hreflang Tags, Meta Tags
"""

import json
import logging
from html import escape as _esc

logger = logging.getLogger(__name__)

# ─── Tool 7: Schema Markup Generator ─────────────────────────────────────────

SCHEMA_TEMPLATES = {
    "article": {
        "fields": [
            {"id": "headline", "label": "Headline", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": True},
            {"id": "author", "label": "Author Name", "type": "text", "required": True},
            {"id": "author_url", "label": "Author Profile URL", "type": "text", "required": False},
            {"id": "publisher", "label": "Publisher Name", "type": "text", "required": True},
            {
                "id": "publisher_logo",
                "label": "Publisher Logo URL",
                "type": "text",
                "required": False,
            },
            {"id": "date_published", "label": "Date Published", "type": "date", "required": True},
            {"id": "date_modified", "label": "Date Modified", "type": "date", "required": False},
            {"id": "image", "label": "Main Image URL", "type": "text", "required": False},
            {"id": "url", "label": "Page URL", "type": "text", "required": True},
        ]
    },
    "faq": {
        "fields": [
            {"id": "faq_items", "label": "FAQ Items", "type": "faq_repeater", "required": True},
        ]
    },
    "product": {
        "fields": [
            {"id": "name", "label": "Product Name", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": True},
            {"id": "image", "label": "Product Image URL", "type": "text", "required": False},
            {"id": "url", "label": "Product Page URL", "type": "text", "required": True},
            {"id": "brand", "label": "Brand", "type": "text", "required": False},
            {"id": "sku", "label": "SKU", "type": "text", "required": False},
            {"id": "price", "label": "Price", "type": "text", "required": False},
            {"id": "currency", "label": "Currency (e.g. USD)", "type": "text", "required": False},
            {
                "id": "availability",
                "label": "Availability",
                "type": "select",
                "required": False,
                "options": ["InStock", "OutOfStock", "PreOrder", "Discontinued"],
            },
            {
                "id": "rating_value",
                "label": "Rating Value (0–5)",
                "type": "text",
                "required": False,
            },
            {"id": "rating_count", "label": "Rating Count", "type": "text", "required": False},
        ]
    },
    "breadcrumb": {
        "fields": [
            {
                "id": "items",
                "label": "Breadcrumb Items",
                "type": "breadcrumb_repeater",
                "required": True,
            },
        ]
    },
    "localbusiness": {
        "fields": [
            {"id": "name", "label": "Business Name", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": False},
            {"id": "url", "label": "Website URL", "type": "text", "required": True},
            {"id": "telephone", "label": "Phone Number", "type": "text", "required": False},
            {"id": "address", "label": "Street Address", "type": "text", "required": False},
            {"id": "city", "label": "City", "type": "text", "required": False},
            {"id": "state", "label": "State/Region", "type": "text", "required": False},
            {"id": "zip", "label": "Postal Code", "type": "text", "required": False},
            {"id": "country", "label": "Country Code (US)", "type": "text", "required": False},
            {"id": "image", "label": "Business Image URL", "type": "text", "required": False},
            {"id": "price_range", "label": "Price Range ($$)", "type": "text", "required": False},
        ]
    },
    "video": {
        "fields": [
            {"id": "name", "label": "Video Title", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": True},
            {"id": "thumbnail_url", "label": "Thumbnail Image URL", "type": "text", "required": True},
            {"id": "upload_date", "label": "Upload Date", "type": "date", "required": True},
            {"id": "duration", "label": "Duration (ISO 8601, e.g. PT2M30S)", "type": "text", "required": False},
            {"id": "content_url", "label": "Video File URL (.mp4)", "type": "text", "required": False},
            {"id": "embed_url", "label": "Embed URL (YouTube/Vimeo)", "type": "text", "required": False},
        ]
    },
    "event": {
        "fields": [
            {"id": "name", "label": "Event Name", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": False},
            {"id": "start_date", "label": "Start Date/Time (ISO 8601)", "type": "text", "required": True},
            {"id": "end_date", "label": "End Date/Time (ISO 8601)", "type": "text", "required": False},
            {"id": "location_name", "label": "Location Name", "type": "text", "required": True},
            {"id": "location_address", "label": "Location Address", "type": "text", "required": False},
            {"id": "image", "label": "Event Image URL", "type": "text", "required": False},
            {"id": "url", "label": "Event Page URL", "type": "text", "required": False},
            {"id": "organizer_name", "label": "Organizer Name", "type": "text", "required": False},
            {"id": "organizer_url", "label": "Organizer URL", "type": "text", "required": False},
            {"id": "offer_price", "label": "Ticket Price", "type": "text", "required": False},
            {"id": "offer_currency", "label": "Currency (e.g. USD)", "type": "text", "required": False},
            {"id": "offer_url", "label": "Ticket URL", "type": "text", "required": False},
            {
                "id": "event_status",
                "label": "Event Status",
                "type": "select",
                "required": False,
                "options": ["EventScheduled", "EventCancelled", "EventPostponed", "EventRescheduled", "EventMovedOnline"],
            },
            {
                "id": "attendance_mode",
                "label": "Attendance Mode",
                "type": "select",
                "required": False,
                "options": ["OfflineEventAttendanceMode", "OnlineEventAttendanceMode", "MixedEventAttendanceMode"],
            },
        ]
    },
    "howto": {
        "fields": [
            {"id": "name", "label": "How-To Title", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": True},
            {"id": "total_time", "label": "Total Time (ISO 8601, e.g. PT30M)", "type": "text", "required": False},
            {"id": "image", "label": "Hero Image URL", "type": "text", "required": False},
            {"id": "supplies", "label": "Supplies (one per line)", "type": "textarea", "required": False},
            {"id": "tools", "label": "Tools (one per line)", "type": "textarea", "required": False},
            {"id": "steps", "label": "Steps", "type": "howto_repeater", "required": True},
        ]
    },
    "person": {
        "fields": [
            {"id": "name", "label": "Full Name", "type": "text", "required": True},
            {"id": "url", "label": "Personal Website / Profile URL", "type": "text", "required": False},
            {"id": "image", "label": "Photo URL", "type": "text", "required": False},
            {"id": "job_title", "label": "Job Title", "type": "text", "required": False},
            {"id": "works_for", "label": "Company / Organization", "type": "text", "required": False},
            {"id": "email", "label": "Email", "type": "text", "required": False},
            {"id": "telephone", "label": "Telephone", "type": "text", "required": False},
            {"id": "same_as", "label": "Social Profile URLs (one per line)", "type": "textarea", "required": False},
        ]
    },
    "organization": {
        "fields": [
            {"id": "name", "label": "Organization Name", "type": "text", "required": True},
            {"id": "url", "label": "Website URL", "type": "text", "required": True},
            {"id": "logo", "label": "Logo URL", "type": "text", "required": False},
            {"id": "description", "label": "Description", "type": "textarea", "required": False},
            {"id": "telephone", "label": "Phone Number", "type": "text", "required": False},
            {"id": "email", "label": "Contact Email", "type": "text", "required": False},
            {"id": "founding_date", "label": "Founding Date (YYYY-MM-DD)", "type": "text", "required": False},
            {"id": "address", "label": "Street Address", "type": "text", "required": False},
            {"id": "city", "label": "City", "type": "text", "required": False},
            {"id": "state", "label": "State/Region", "type": "text", "required": False},
            {"id": "zip", "label": "Postal Code", "type": "text", "required": False},
            {"id": "country", "label": "Country Code (US)", "type": "text", "required": False},
            {"id": "same_as", "label": "Social Profile URLs (one per line)", "type": "textarea", "required": False},
        ]
    },
    "recipe": {
        "fields": [
            {"id": "name", "label": "Recipe Name", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": True},
            {"id": "image", "label": "Image URL", "type": "text", "required": True},
            {"id": "author", "label": "Author Name", "type": "text", "required": True},
            {"id": "date_published", "label": "Date Published", "type": "date", "required": False},
            {"id": "prep_time", "label": "Prep Time (e.g. PT15M)", "type": "text", "required": False},
            {"id": "cook_time", "label": "Cook Time (e.g. PT30M)", "type": "text", "required": False},
            {"id": "total_time", "label": "Total Time (e.g. PT45M)", "type": "text", "required": False},
            {"id": "recipe_yield", "label": "Yield (e.g. 4 servings)", "type": "text", "required": False},
            {"id": "recipe_category", "label": "Category (e.g. Dessert)", "type": "text", "required": False},
            {"id": "recipe_cuisine", "label": "Cuisine (e.g. Italian)", "type": "text", "required": False},
            {"id": "calories", "label": "Calories per serving", "type": "text", "required": False},
            {"id": "ingredients", "label": "Ingredients (one per line)", "type": "textarea", "required": True},
            {"id": "instructions", "label": "Instructions (one step per line)", "type": "textarea", "required": True},
        ]
    },
    "jobposting": {
        "fields": [
            {"id": "title", "label": "Job Title", "type": "text", "required": True},
            {"id": "description", "label": "Job Description (HTML allowed)", "type": "textarea", "required": True},
            {"id": "date_posted", "label": "Date Posted", "type": "date", "required": True},
            {"id": "valid_through", "label": "Valid Through", "type": "date", "required": False},
            {"id": "employment_type", "label": "Employment Type", "type": "select", "required": False,
             "options": ["FULL_TIME", "PART_TIME", "CONTRACTOR", "TEMPORARY", "INTERN", "VOLUNTEER", "PER_DIEM", "OTHER"]},
            {"id": "hiring_org", "label": "Hiring Organization", "type": "text", "required": True},
            {"id": "hiring_org_url", "label": "Organization URL", "type": "text", "required": False},
            {"id": "hiring_org_logo", "label": "Organization Logo URL", "type": "text", "required": False},
            {"id": "address", "label": "Job Location Street", "type": "text", "required": False},
            {"id": "city", "label": "City", "type": "text", "required": True},
            {"id": "state", "label": "State/Region", "type": "text", "required": False},
            {"id": "zip", "label": "Postal Code", "type": "text", "required": False},
            {"id": "country", "label": "Country Code (US)", "type": "text", "required": True},
            {"id": "salary_min", "label": "Salary Min", "type": "text", "required": False},
            {"id": "salary_max", "label": "Salary Max", "type": "text", "required": False},
            {"id": "salary_currency", "label": "Salary Currency (e.g. USD)", "type": "text", "required": False},
            {"id": "salary_unit", "label": "Salary Unit", "type": "select", "required": False,
             "options": ["HOUR", "DAY", "WEEK", "MONTH", "YEAR"]},
        ]
    },
    "course": {
        "fields": [
            {"id": "name", "label": "Course Name", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": True},
            {"id": "provider_name", "label": "Provider Name", "type": "text", "required": True},
            {"id": "provider_url", "label": "Provider URL", "type": "text", "required": False},
            {"id": "url", "label": "Course Page URL", "type": "text", "required": False},
        ]
    },
    "review": {
        "fields": [
            {"id": "item_name", "label": "Item Reviewed (e.g. product name)", "type": "text", "required": True},
            {"id": "item_type", "label": "Item Type", "type": "select", "required": False,
             "options": ["Product", "Book", "Movie", "Restaurant", "Service", "Organization"]},
            {"id": "rating_value", "label": "Rating (0–5)", "type": "text", "required": True},
            {"id": "rating_best", "label": "Best Rating (default 5)", "type": "text", "required": False},
            {"id": "author", "label": "Reviewer Name", "type": "text", "required": True},
            {"id": "review_body", "label": "Review Text", "type": "textarea", "required": False},
            {"id": "date_published", "label": "Date Published", "type": "date", "required": False},
        ]
    },
    "softwareapp": {
        "fields": [
            {"id": "name", "label": "App Name", "type": "text", "required": True},
            {"id": "description", "label": "Description", "type": "textarea", "required": False},
            {"id": "operating_system", "label": "OS (e.g. iOS, Android, Web)", "type": "text", "required": True},
            {"id": "application_category", "label": "Category (e.g. ProductivityApplication)", "type": "text", "required": True},
            {"id": "url", "label": "App URL / Store URL", "type": "text", "required": False},
            {"id": "image", "label": "Icon / Screenshot URL", "type": "text", "required": False},
            {"id": "price", "label": "Price (0 for free)", "type": "text", "required": False},
            {"id": "currency", "label": "Currency (e.g. USD)", "type": "text", "required": False},
            {"id": "rating_value", "label": "Rating Value", "type": "text", "required": False},
            {"id": "rating_count", "label": "Rating Count", "type": "text", "required": False},
        ]
    },
}


def generate_schema(schema_type: str, data: dict) -> dict:
    """Generate JSON-LD schema markup from form data."""
    schema_type = schema_type.lower()
    if schema_type not in SCHEMA_TEMPLATES:
        return {"ok": False, "error": f"Unknown schema type: {schema_type}"}

    try:
        if schema_type == "article":
            obj = {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": data.get("headline", ""),
                "description": data.get("description", ""),
                "author": {"@type": "Person", "name": data.get("author", "")},
                "publisher": {
                    "@type": "Organization",
                    "name": data.get("publisher", ""),
                },
                "datePublished": data.get("date_published", ""),
                "url": data.get("url", ""),
            }
            if data.get("author_url"):
                obj["author"]["url"] = data["author_url"]
            if data.get("publisher_logo"):
                obj["publisher"]["logo"] = {"@type": "ImageObject", "url": data["publisher_logo"]}
            if data.get("date_modified"):
                obj["dateModified"] = data["date_modified"]
            if data.get("image"):
                obj["image"] = data["image"]

        elif schema_type == "faq":
            items = data.get("faq_items", [])
            obj = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item.get("question", ""),
                        "acceptedAnswer": {"@type": "Answer", "text": item.get("answer", "")},
                    }
                    for item in items
                    if item.get("question")
                ],
            }

        elif schema_type == "product":
            obj = {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "url": data.get("url", ""),
            }
            if data.get("image"):
                obj["image"] = data["image"]
            if data.get("brand"):
                obj["brand"] = {"@type": "Brand", "name": data["brand"]}
            if data.get("sku"):
                obj["sku"] = data["sku"]
            if data.get("price") or data.get("availability"):
                offer = {"@type": "Offer"}
                if data.get("price"):
                    offer["price"] = data["price"]
                if data.get("currency"):
                    offer["priceCurrency"] = data["currency"]
                if data.get("availability"):
                    offer["availability"] = f"https://schema.org/{data['availability']}"
                obj["offers"] = offer
            if data.get("rating_value"):
                obj["aggregateRating"] = {
                    "@type": "AggregateRating",
                    "ratingValue": data["rating_value"],
                    "reviewCount": data.get("rating_count", "1"),
                }

        elif schema_type == "breadcrumb":
            items = data.get("items", [])
            obj = {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "name": item.get("name", ""),
                        "item": item.get("url", ""),
                    }
                    for i, item in enumerate(items)
                    if item.get("name")
                ],
            }

        elif schema_type == "localbusiness":
            obj = {
                "@context": "https://schema.org",
                "@type": "LocalBusiness",
                "name": data.get("name", ""),
                "url": data.get("url", ""),
            }
            if data.get("description"):
                obj["description"] = data["description"]
            if data.get("telephone"):
                obj["telephone"] = data["telephone"]
            if data.get("image"):
                obj["image"] = data["image"]
            if data.get("price_range"):
                obj["priceRange"] = data["price_range"]
            addr_parts = {
                k: data.get(k)
                for k in ["address", "city", "state", "zip", "country"]
                if data.get(k)
            }
            if addr_parts:
                obj["address"] = {
                    "@type": "PostalAddress",
                    "streetAddress": addr_parts.get("address", ""),
                    "addressLocality": addr_parts.get("city", ""),
                    "addressRegion": addr_parts.get("state", ""),
                    "postalCode": addr_parts.get("zip", ""),
                    "addressCountry": addr_parts.get("country", ""),
                }
        elif schema_type == "video":
            obj = {
                "@context": "https://schema.org",
                "@type": "VideoObject",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "thumbnailUrl": data.get("thumbnail_url", ""),
                "uploadDate": data.get("upload_date", ""),
            }
            if data.get("duration"):
                obj["duration"] = data["duration"]
            if data.get("content_url"):
                obj["contentUrl"] = data["content_url"]
            if data.get("embed_url"):
                obj["embedUrl"] = data["embed_url"]

        elif schema_type == "event":
            obj = {
                "@context": "https://schema.org",
                "@type": "Event",
                "name": data.get("name", ""),
                "startDate": data.get("start_date", ""),
                "location": {
                    "@type": "Place",
                    "name": data.get("location_name", ""),
                },
                "eventStatus": f"https://schema.org/{data.get('event_status', 'EventScheduled')}",
                "eventAttendanceMode": f"https://schema.org/{data.get('attendance_mode', 'OfflineEventAttendanceMode')}",
            }
            if data.get("description"):
                obj["description"] = data["description"]
            if data.get("end_date"):
                obj["endDate"] = data["end_date"]
            if data.get("location_address"):
                obj["location"]["address"] = data["location_address"]
            if data.get("image"):
                obj["image"] = data["image"]
            if data.get("url"):
                obj["url"] = data["url"]
            if data.get("organizer_name"):
                org = {"@type": "Organization", "name": data["organizer_name"]}
                if data.get("organizer_url"):
                    org["url"] = data["organizer_url"]
                obj["organizer"] = org
            if data.get("offer_price"):
                offer = {
                    "@type": "Offer",
                    "price": data["offer_price"],
                    "priceCurrency": data.get("offer_currency", "USD"),
                    "availability": "https://schema.org/InStock",
                }
                if data.get("offer_url"):
                    offer["url"] = data["offer_url"]
                obj["offers"] = offer

        elif schema_type == "howto":
            steps_text = data.get("steps", [])
            if isinstance(steps_text, str):
                steps_list = [s.strip() for s in steps_text.splitlines() if s.strip()]
            elif isinstance(steps_text, list):
                steps_list = [
                    s.get("text", "") if isinstance(s, dict) else str(s)
                    for s in steps_text
                    if s
                ]
            else:
                steps_list = []
            obj = {
                "@context": "https://schema.org",
                "@type": "HowTo",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "step": [
                    {
                        "@type": "HowToStep",
                        "position": i + 1,
                        "text": step,
                    }
                    for i, step in enumerate(steps_list)
                ],
            }
            if data.get("total_time"):
                obj["totalTime"] = data["total_time"]
            if data.get("image"):
                obj["image"] = data["image"]
            if data.get("supplies"):
                supplies = [s.strip() for s in str(data["supplies"]).splitlines() if s.strip()]
                obj["supply"] = [{"@type": "HowToSupply", "name": s} for s in supplies]
            if data.get("tools"):
                tools = [s.strip() for s in str(data["tools"]).splitlines() if s.strip()]
                obj["tool"] = [{"@type": "HowToTool", "name": t} for t in tools]

        elif schema_type == "person":
            obj = {
                "@context": "https://schema.org",
                "@type": "Person",
                "name": data.get("name", ""),
            }
            for src, dst in [
                ("url", "url"),
                ("image", "image"),
                ("job_title", "jobTitle"),
                ("email", "email"),
                ("telephone", "telephone"),
            ]:
                if data.get(src):
                    obj[dst] = data[src]
            if data.get("works_for"):
                obj["worksFor"] = {"@type": "Organization", "name": data["works_for"]}
            if data.get("same_as"):
                links = [s.strip() for s in str(data["same_as"]).splitlines() if s.strip()]
                if links:
                    obj["sameAs"] = links

        elif schema_type == "organization":
            obj = {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": data.get("name", ""),
                "url": data.get("url", ""),
            }
            if data.get("logo"):
                obj["logo"] = data["logo"]
            for src, dst in [
                ("description", "description"),
                ("telephone", "telephone"),
                ("email", "email"),
                ("founding_date", "foundingDate"),
            ]:
                if data.get(src):
                    obj[dst] = data[src]
            addr_parts = {
                k: data.get(k)
                for k in ["address", "city", "state", "zip", "country"]
                if data.get(k)
            }
            if addr_parts:
                obj["address"] = {
                    "@type": "PostalAddress",
                    "streetAddress": addr_parts.get("address", ""),
                    "addressLocality": addr_parts.get("city", ""),
                    "addressRegion": addr_parts.get("state", ""),
                    "postalCode": addr_parts.get("zip", ""),
                    "addressCountry": addr_parts.get("country", ""),
                }
            if data.get("same_as"):
                links = [s.strip() for s in str(data["same_as"]).splitlines() if s.strip()]
                if links:
                    obj["sameAs"] = links

        elif schema_type == "recipe":
            ings = [s.strip() for s in str(data.get("ingredients", "")).splitlines() if s.strip()]
            steps = [s.strip() for s in str(data.get("instructions", "")).splitlines() if s.strip()]
            obj = {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "image": data.get("image", ""),
                "author": {"@type": "Person", "name": data.get("author", "")},
                "recipeIngredient": ings,
                "recipeInstructions": [
                    {"@type": "HowToStep", "position": i + 1, "text": s}
                    for i, s in enumerate(steps)
                ],
            }
            for src, dst in [
                ("date_published", "datePublished"),
                ("prep_time", "prepTime"),
                ("cook_time", "cookTime"),
                ("total_time", "totalTime"),
                ("recipe_yield", "recipeYield"),
                ("recipe_category", "recipeCategory"),
                ("recipe_cuisine", "recipeCuisine"),
            ]:
                if data.get(src):
                    obj[dst] = data[src]
            if data.get("calories"):
                obj["nutrition"] = {
                    "@type": "NutritionInformation",
                    "calories": f"{data['calories']} calories",
                }

        elif schema_type == "jobposting":
            obj = {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "datePosted": data.get("date_posted", ""),
                "hiringOrganization": {
                    "@type": "Organization",
                    "name": data.get("hiring_org", ""),
                },
                "jobLocation": {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": data.get("city", ""),
                        "addressCountry": data.get("country", ""),
                    },
                },
            }
            if data.get("hiring_org_url"):
                obj["hiringOrganization"]["sameAs"] = data["hiring_org_url"]
            if data.get("hiring_org_logo"):
                obj["hiringOrganization"]["logo"] = data["hiring_org_logo"]
            if data.get("address"):
                obj["jobLocation"]["address"]["streetAddress"] = data["address"]
            if data.get("state"):
                obj["jobLocation"]["address"]["addressRegion"] = data["state"]
            if data.get("zip"):
                obj["jobLocation"]["address"]["postalCode"] = data["zip"]
            if data.get("employment_type"):
                obj["employmentType"] = data["employment_type"]
            if data.get("valid_through"):
                obj["validThrough"] = data["valid_through"]
            if data.get("salary_min") or data.get("salary_max"):
                value = {
                    "@type": "QuantitativeValue",
                    "unitText": data.get("salary_unit", "YEAR"),
                }
                if data.get("salary_min") and data.get("salary_max"):
                    value["minValue"] = data["salary_min"]
                    value["maxValue"] = data["salary_max"]
                else:
                    value["value"] = data.get("salary_min") or data.get("salary_max")
                obj["baseSalary"] = {
                    "@type": "MonetaryAmount",
                    "currency": data.get("salary_currency", "USD"),
                    "value": value,
                }

        elif schema_type == "course":
            obj = {
                "@context": "https://schema.org",
                "@type": "Course",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "provider": {
                    "@type": "Organization",
                    "name": data.get("provider_name", ""),
                },
            }
            if data.get("provider_url"):
                obj["provider"]["sameAs"] = data["provider_url"]
            if data.get("url"):
                obj["url"] = data["url"]

        elif schema_type == "review":
            obj = {
                "@context": "https://schema.org",
                "@type": "Review",
                "itemReviewed": {
                    "@type": data.get("item_type", "Product"),
                    "name": data.get("item_name", ""),
                },
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": data.get("rating_value", ""),
                    "bestRating": data.get("rating_best", "5"),
                },
                "author": {"@type": "Person", "name": data.get("author", "")},
            }
            if data.get("review_body"):
                obj["reviewBody"] = data["review_body"]
            if data.get("date_published"):
                obj["datePublished"] = data["date_published"]

        elif schema_type == "softwareapp":
            obj = {
                "@context": "https://schema.org",
                "@type": "SoftwareApplication",
                "name": data.get("name", ""),
                "operatingSystem": data.get("operating_system", ""),
                "applicationCategory": data.get("application_category", ""),
            }
            if data.get("description"):
                obj["description"] = data["description"]
            if data.get("url"):
                obj["url"] = data["url"]
            if data.get("image"):
                obj["image"] = data["image"]
            if data.get("price") is not None and str(data.get("price", "")).strip() != "":
                obj["offers"] = {
                    "@type": "Offer",
                    "price": data["price"],
                    "priceCurrency": data.get("currency", "USD"),
                }
            if data.get("rating_value"):
                obj["aggregateRating"] = {
                    "@type": "AggregateRating",
                    "ratingValue": data["rating_value"],
                    "ratingCount": data.get("rating_count", "1"),
                }

        else:
            return {"ok": False, "error": "Unhandled schema type"}

        markup = f'<script type="application/ld+json">\n{json.dumps(obj, indent=2)}\n</script>'
        warnings = []
        for field in SCHEMA_TEMPLATES[schema_type]["fields"]:
            if field.get("required") and not str(data.get(field["id"], "")).strip():
                warnings.append(f"Missing required field: {field['label']}")
        return {"ok": True, "schema_type": schema_type, "markup": markup, "json": obj, "warnings": warnings}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        logger.exception("generate_schema failed for %s", schema_type)
        return {"ok": False, "error": str(e)}


def get_schema_fields(schema_type: str) -> dict:
    st = schema_type.lower()
    if st not in SCHEMA_TEMPLATES:
        return {"ok": False, "error": "Unknown schema type"}
    return {"ok": True, "schema_type": st, "fields": SCHEMA_TEMPLATES[st]["fields"]}


# ─── Tool 8: robots.txt Generator ────────────────────────────────────────────


def generate_robots_txt(data: dict) -> dict:
    """
    Build a robots.txt from structured form data.
    data keys:
      rules:  [{user_agent, allow:[], disallow:[]}]
      sitemap: str (optional sitemap URL)
      crawl_delay: int (optional)
    """
    def _clean(s: object) -> str:
        # Strip CR/LF so a value can't inject a new directive line
        return str(s).replace("\r", " ").replace("\n", " ").strip()

    try:
        warnings: list[str] = []
        lines: list[str] = []
        rules = data.get("rules", [])
        if not rules:
            rules = [{"user_agent": "*", "disallow": [], "allow": []}]

        for rule in rules:
            ua = _clean(rule.get("user_agent", "*")) or "*"
            lines.append(f"User-agent: {ua}")
            raw_delay = rule.get("crawl_delay", "") or data.get("crawl_delay", "")
            for path in rule.get("disallow") or []:
                if path:
                    lines.append(f"Disallow: {_clean(path)}")
            for path in rule.get("allow") or []:
                if path:
                    lines.append(f"Allow: {_clean(path)}")
            if raw_delay not in (None, ""):
                try:
                    float(raw_delay)
                    lines.append(f"Crawl-delay: {_clean(raw_delay)}")
                except (TypeError, ValueError):
                    warnings.append(f"Dropped non-numeric crawl_delay '{raw_delay}' for {ua}")
            lines.append("")

        if data.get("sitemap"):
            lines.append(f"Sitemap: {_clean(data['sitemap'])}")

        return {"ok": True, "content": "\n".join(lines).strip(), "warnings": warnings}
    except (ValueError, TypeError) as e:
        from tools._common import safe_error
        logger.exception("generate_robots_txt failed")
        return {"ok": False, "error": safe_error(e)}


# ─── Tool 9: XML Sitemap Generator ───────────────────────────────────────────


def generate_sitemap(data: dict) -> dict:
    """
    Build an XML sitemap from a list of URL entries.
    data keys:
      urls: [{url, lastmod, changefreq, priority}]
    """
    from urllib.parse import urlparse

    from tools._common import xml_text

    _VALID_CHANGEFREQ = {"always", "hourly", "daily", "weekly", "monthly", "yearly", "never"}
    try:
        urls = data.get("urls", [])
        if not urls:
            return {"ok": False, "error": "At least one URL is required"}

        warnings: list[str] = []
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        count = 0
        for entry in urls:
            url = (entry.get("url") or "").strip()
            if not url:
                continue
            if urlparse(url).scheme not in ("http", "https"):
                warnings.append(f"Skipped URL with invalid scheme: {url}")
                continue
            lines.append("  <url>")
            lines.append(f"    <loc>{xml_text(url)}</loc>")
            if entry.get("lastmod"):
                lines.append(f"    <lastmod>{xml_text(entry['lastmod'])}</lastmod>")
            cf = (entry.get("changefreq") or "").strip().lower()
            if cf:
                if cf in _VALID_CHANGEFREQ:
                    lines.append(f"    <changefreq>{xml_text(cf)}</changefreq>")
                else:
                    warnings.append(f"Dropped invalid changefreq '{cf}' for {url}")
            pr = entry.get("priority")
            if pr not in (None, ""):
                try:
                    pf = float(pr)
                    if 0.0 <= pf <= 1.0:
                        lines.append(f"    <priority>{xml_text(pr)}</priority>")
                    else:
                        warnings.append(f"Dropped out-of-range priority '{pr}' for {url} (must be 0.0-1.0)")
                except (TypeError, ValueError):
                    warnings.append(f"Dropped non-numeric priority '{pr}' for {url}")
            lines.append("  </url>")
            count += 1

        lines.append("</urlset>")
        return {"ok": True, "content": "\n".join(lines), "url_count": count, "warnings": warnings}
    except (ValueError, TypeError) as e:
        from tools._common import safe_error
        logger.exception("generate_sitemap failed")
        return {"ok": False, "error": safe_error(e)}


# ─── Tool 10: Hreflang Tag Generator ─────────────────────────────────────────


def generate_hreflang(data: dict) -> dict:
    """
    Build hreflang link elements from a list of {locale, url} pairs.
    data keys:
      items: [{locale, url}]
      include_xdefault: bool
      xdefault_url: str
    """
    import re
    from urllib.parse import urlparse

    from tools._common import xml_text

    _LOCALE_RE = re.compile(r"^([a-z]{2,3}(-[A-Za-z0-9]{2,8})?|x-default)$", re.IGNORECASE)
    try:
        items = data.get("items", [])
        if not items:
            return {"ok": False, "error": "At least one locale/URL pair is required"}

        warnings: list[str] = []
        tags: list[str] = []
        header_vals: list[str] = []
        for item in items:
            locale = (item.get("locale") or "").strip()
            url = (item.get("url") or "").strip()
            if not locale or not url:
                continue
            if not _LOCALE_RE.match(locale):
                warnings.append(f"Dropped invalid locale '{locale}' (expected e.g. en, en-US, x-default)")
                continue
            if urlparse(url).scheme not in ("http", "https"):
                warnings.append(f"Dropped URL with invalid scheme for locale '{locale}': {url}")
                continue
            tags.append(f'<link rel="alternate" hreflang="{xml_text(locale)}" href="{xml_text(url)}">')
            header_vals.append(f'<{xml_text(url)}>; rel="alternate"; hreflang="{xml_text(locale)}"')

        if data.get("include_xdefault") and data.get("xdefault_url"):
            xd = str(data["xdefault_url"]).strip()
            if urlparse(xd).scheme in ("http", "https"):
                tags.append(f'<link rel="alternate" hreflang="x-default" href="{xml_text(xd)}">')
            else:
                warnings.append(f"Dropped x-default URL with invalid scheme: {xd}")

        if not tags:
            return {"ok": False, "error": "No valid locale/URL pairs found", "warnings": warnings}

        return {
            "ok": True,
            "html_tags": "\n".join(tags),
            "http_header": "Link: " + ", ".join(header_vals) if header_vals else "",
            "count": len(tags),
            "warnings": warnings,
        }
    except (ValueError, TypeError) as e:
        from tools._common import safe_error
        logger.exception("generate_hreflang failed")
        return {"ok": False, "error": safe_error(e)}


# ─── Tool 11: Meta Tags Generator ────────────────────────────────────────────


def generate_meta_tags(data: dict) -> dict:
    """
    Generate a complete <head> meta block including primary, OG and Twitter tags.
    data keys: title, description, keywords, canonical, robots,
               og_title, og_description, og_image, og_type, og_url, og_site_name,
               tw_card, tw_title, tw_description, tw_image, tw_site
    """
    try:
        lines = ["<!-- Primary Meta Tags -->"]

        t = data.get("title", "")
        d = data.get("description", "")
        k = data.get("keywords", "")
        c = data.get("canonical", "")
        r = data.get("robots", "")

        # HTML-escape all user-supplied values before interpolation so the
        # generated markup is safe to display and copy-paste.
        te, de, ke, ce, re_ = _esc(t), _esc(d), _esc(k), _esc(c), _esc(r)

        if t:
            lines.append(f"<title>{te}</title>")
        if t:
            lines.append(f'<meta name="title" content="{te}">')
        if d:
            lines.append(f'<meta name="description" content="{de}">')
        if k:
            lines.append(f'<meta name="keywords" content="{ke}">')
        if r:
            lines.append(f'<meta name="robots" content="{re_}">')
        if c:
            lines.append(f'<link rel="canonical" href="{ce}">')

        # Open Graph
        og_fields = {
            "og:type":        _esc(data.get("og_type", "website")),
            "og:url":         _esc(data.get("og_url", c)),
            "og:title":       _esc(data.get("og_title", t)),
            "og:description": _esc(data.get("og_description", d)),
            "og:image":       _esc(data.get("og_image", "")),
            "og:site_name":   _esc(data.get("og_site_name", "")),
        }
        og_lines = [f'<meta property="{k}" content="{v}">' for k, v in og_fields.items() if v]
        if og_lines:
            lines.append("\n<!-- Open Graph / Facebook -->")
            lines.extend(og_lines)

        # Twitter / X
        tw_fields = {
            "twitter:card":        _esc(data.get("tw_card", "summary_large_image")),
            "twitter:url":         _esc(data.get("og_url", c)),
            "twitter:title":       _esc(data.get("tw_title", t)),
            "twitter:description": _esc(data.get("tw_description", d)),
            "twitter:image":       _esc(data.get("tw_image", data.get("og_image", ""))),
            "twitter:site":        _esc(data.get("tw_site", "")),
        }
        tw_lines = [f'<meta name="{k}" content="{v}">' for k, v in tw_fields.items() if v]
        if tw_lines:
            lines.append("\n<!-- Twitter -->")
            lines.extend(tw_lines)

        content = "\n".join(lines)

        warnings = []
        if not t:
            warnings.append("Title is missing")
        elif len(t) > 60:
            warnings.append(f"Title is {len(t)} chars (recommended ≤60)")
        if not d:
            warnings.append("Description is missing")
        elif len(d) > 160:
            warnings.append(f"Description is {len(d)} chars (recommended ≤160)")
        if not c:
            warnings.append("Canonical URL not set")
        if not data.get("og_image") and not data.get("tw_image"):
            warnings.append("No social sharing image set (og:image / twitter:image)")

        return {"ok": True, "content": content, "warnings": warnings}
    except (ValueError, TypeError, KeyError) as e:
        logger.exception("generate_meta_tags failed")
        return {"ok": False, "error": str(e)}
