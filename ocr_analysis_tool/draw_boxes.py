import io

import pymupdf
from PIL import Image


def get_rect(bounding_box: list) -> pymupdf.Rect:
    """
    Get rectangle shape for the provided bounding box (coordinates of each corner in the box)

    Args
        bounding_box: list containing the coordinates [x,y] of the corners of the box in inches, [[lower left], [lower right], [upper right], [upper left]]

    Returns
        rect: fitz rectangle for on image
    """
    # Convert bounding box from inches to points (1 point = 1/72 inch)
    bounding_box_points = [coord * 72 for pair in bounding_box for coord in pair]
    # Create a rectangle for the bounding box (lower left and upper right cornet of bounding box)
    rect = pymupdf.Rect(bounding_box_points[:2] + bounding_box_points[4:6])
    return rect


def convert_polygon_bb(polygon: list):
    """
    Convert a polygon to a bounding box we can use

    Args
        polygon: list containing the coordinates of the corners of the bounding box, [lower left, lower right, upper right, upper left]

    Returns
        bounding_box: list containing the coordinates [x,y] of the corners of the box in inches, [[lower left], [lower right], [upper right], [upper left]]
    """
    lower_left = [polygon[0], polygon[1]]
    lower_right = [polygon[2], polygon[3]]
    upper_right = [polygon[4], polygon[5]]
    upper_left = [polygon[6], polygon[7]]

    bounding_box = [lower_left, lower_right, upper_right, upper_left]
    return bounding_box


def draw_rect_pages(doc: pymupdf.Document, pages: dict, color: tuple, c_width: float):
    """
    Draw the rectangle on the pages of the pdf document

    Args
        doc: pdf document
        pages: contains the page number and the polygon (bounding box)
        color: RGB colors of rectangles to draw
        c_width: width of the rectangles to draw

    Returns
        doc: document with drawn rectangles
    """
    for page in pages:
        page_number = page["page_number"] - 1  # Adjusting page number to 0-based index
        bounding_box = [[coords["x"], coords["y"]] for coords in page["polygon"]]
        page = doc.load_page(page_number)
        page.draw_rect(get_rect(bounding_box), color=color, width=c_width)

    return doc


def update_min_max_box(current_box: list, box_to_check: list):
    """
    Check if the min and max coordinates of a bounding box need to be updated. The goal is to return the largest bounding box given the coordinates.
    Format of boxes needs to be: [[lower left], [lower right], [upper right], [upper left]]

    Args
        current_box: bounding box with current min and max coordinates for each corner of the box
        box_to_check: bounding box to compare with the current box

    Return
        min_max_box: largest bounding box containing the two input boxes
    """
    # If we have no 'current_box', just use 'box_to_check'
    if current_box is None:
        return box_to_check

    # Combine all corners from both boxes
    all_points = current_box + box_to_check

    # Extract all x and y coordinates
    xs = [pt[0] for pt in all_points]
    ys = [pt[1] for pt in all_points]

    # Determine global min/max for x and y
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Construct the updated bounding box in the required format
    min_max_box = [
        [min_x, min_y],  # lower left
        [max_x, min_y],  # lower right
        [max_x, max_y],  # upper right
        [min_x, max_y],  # upper left
    ]

    return min_max_box


def draw_bounding_boxes_on_pdf(
    pdf_path, content_data: dict = None, kv_data: list = None, invoice_data: dict = None
):
    doc = pymupdf.open(pdf_path)

    modified_images = []

    # draw rectangles over all recognized text
    if content_data:
        for page in content_data["pages"]:
            page_number = page["pageNumber"] - 1  # Adjusting page number to 0-based index
            for word in page["words"]:
                bounding_box = convert_polygon_bb(word["polygon"])
                page = doc.load_page(page_number)
                page.draw_rect(
                    get_rect(bounding_box), color=(1, 0, 0), width=1.8
                )  # red color, slightly thicker line

    # draw rectangles over all key value pairs
    if kv_data:
        for pair in kv_data:

            min_max_boxes = {
                page: None for page in range(len(pair["key"]["boundingRegions"]))
            }
            # Draw keys in green
            for region in pair["key"]["boundingRegions"]:
                page_number = (
                    region["pageNumber"] - 1
                )  # Adjusting page number to 0-based index
                bounding_box = convert_polygon_bb(region["polygon"])
                page = doc.load_page(page_number)
                page.draw_rect(
                    get_rect(bounding_box), color=(0, 1, 0), width=1.8
                )  # green color, slightly thicker line

                min_max_boxes[page_number] = update_min_max_box(
                    min_max_boxes[page_number], bounding_box
                )

            # Draw values in blue
            for region in pair.get("value", {}).get("boundingRegions", []):
                page_number = (
                    region["pageNumber"] - 1
                )  # Adjusting page number to 0-based index
                bounding_box = convert_polygon_bb(region["polygon"])
                page = doc.load_page(page_number)
                page.draw_rect(
                    get_rect(bounding_box), color=(0, 0, 1), width=1.8
                )  # blue color, slightly thicker line

                min_max_boxes[page_number] = update_min_max_box(
                    min_max_boxes[page_number], bounding_box
                )

            # Draw key value pair region in red
            for page_number, box in min_max_boxes.items():
                page = doc.load_page(page_number)
                page.draw_rect(
                    get_rect(box), color=(1, 0, 0), width=0.8
                )  # red color, slightly thinner line

    # draw rectangles over all text categorized by invoice model
    if invoice_data:
        for field, data in invoice_data["fields"].items():
            if field == "Items":
                for value in data["value"]:
                    doc = draw_rect_pages(doc, value["bounding_regions"], (0, 0, 1), 1.0)
                    for v_data in value["value"].values():
                        doc = draw_rect_pages(
                            doc, v_data["bounding_regions"], (0, 1, 0), 0.9
                        )
            if field == "PaymentDetails":
                for value in data["value"]:
                    for v_data in value["value"].values():
                        doc = draw_rect_pages(
                            doc, v_data["bounding_regions"], (0, 1, 0), 0.9
                        )
            else:
                doc = draw_rect_pages(doc, data["bounding_regions"], (0, 0, 1), 1.0)

    # Save image
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img_data = pix.tobytes("png")  # convert the pixmap to PNG bytes
        image = Image.open(io.BytesIO(img_data))
        modified_images.append(image)

    doc.close()
    return modified_images
