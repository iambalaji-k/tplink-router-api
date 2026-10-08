from PIL import Image, ImageDraw

def create_favicon():
    img = Image.new("RGBA", (64, 64), (15, 19, 29, 255))
    d = ImageDraw.Draw(img)
    # Outer border
    d.rounded_rectangle([(1, 1), (62, 62)], radius=14, outline=(0, 167, 225, 120), width=2)
    # Antennas
    d.line([(18, 14), (18, 34)], fill=(124, 208, 255), width=3)
    d.line([(32, 8), (32, 34)], fill=(124, 208, 255), width=3)
    d.line([(46, 14), (46, 34)], fill=(124, 208, 255), width=3)
    # Base
    d.rounded_rectangle([(10, 34), (54, 52)], radius=5, fill=(28, 31, 42), outline=(0, 167, 225), width=2)
    # LEDs
    d.ellipse([(16, 41), (20, 45)], fill=(78, 222, 163))
    d.ellipse([(25, 41), (29, 45)], fill=(0, 167, 225))
    d.ellipse([(34, 41), (38, 45)], fill=(0, 167, 225))
    d.ellipse([(43, 41), (47, 45)], fill=(255, 185, 95))

    img.save("ui/favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("ui/favicon.ico generated successfully.")

if __name__ == "__main__":
    create_favicon()
