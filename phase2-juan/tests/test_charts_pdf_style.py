import io

import matplotlib.image as mpimg

from simlab.charts import _generate_chart_image


def test_pdf_chart_images_are_high_resolution_for_tfg_reports():
    spec = {
        "type": "line",
        "title": "Evolución de recompensa acumulada",
        "x_label": "Paso",
        "y_label": "Recompensa acumulada",
        "series": [
            {
                "name": "drive_reduction_rl",
                "data": [{"x": step, "y": step * 0.7} for step in range(30)],
            },
            {
                "name": "pi_negative_feedback",
                "data": [{"x": step, "y": step * 0.5} for step in range(30)],
            },
        ],
    }

    png = _generate_chart_image(spec)
    assert png is not None

    image = mpimg.imread(io.BytesIO(png), format="png")
    height, width = image.shape[:2]

    assert width >= 1700
    assert height >= 1000
