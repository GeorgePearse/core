## Gemini Integration

This document outlines the integration of Gemini models within the project, covering authentication, model selection, and data formats.

### API Keys and Authentication

To use Gemini models, you need to configure your API key. The application looks for the API key in the `GEMINI_API_KEY` environment variable.

```bash
export GEMINI_API_KEY="YOUR_API_KEY"
```

Authentication is handled automatically by the client library, which will pick up the key from the environment. Ensure that the key has the necessary permissions to access the desired models.

### Model Selection

The model can be selected by specifying the model name in the configuration. The following models are recommended for their respective tasks:

*   **`gemini-pro`:** For general-purpose text generation and understanding.
*   **`gemini-pro-vision`:** For tasks that involve understanding and processing both text and images.
*   **`gemini-ultra`:** For the most complex and demanding tasks.

The default model is `gemini-pro`.

### Input/Output Formats

The input and output formats are designed to be simple and flexible, primarily using JSON.

**Text-only Input:**

For text-based models like `gemini-pro`, the input is a JSON object with a `prompt` field:

```json
{
  "prompt": "Translate 'hello' to French."
}
```

**Multi-modal Input (Text and Image):**

For vision models like `gemini-pro-vision`, the input includes both text and image data. The image should be base64-encoded:

```json
{
  "prompt": "What is in this image?",
  "image": {
    "data": "<base64-encoded-image>",
    "mime_type": "image/png"
  }
}
```

**Output:**

The output from the model is a JSON object containing the generated content:

```json
{
  "result": "Bonjour"
}
```

## "Copy-Paste" Augmentation Research

Here are some key research papers related to the "Copy-Paste" data augmentation technique for computer vision tasks:

### 1. Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation

*   **Link:** [https://arxiv.org/abs/2012.07177](https://arxiv.org/abs/2012.07177)
*   **Description:** This is a foundational paper that demonstrates the effectiveness of a simple copy-paste technique for instance segmentation. The authors show that randomly pasting objects from one image to another, without any complex blending or context modeling, can significantly improve performance, especially for rare object categories. The method is shown to be additive with other augmentation techniques and semi-supervised learning.

### 2. Contextual Copy-Paste for Object Detection

*   **Link:** [https://www.spiedigitallibrary.org/conference-proceedings-of-spie/11512/115121L/Contextual-copy-paste-data-augmentation-for-object-detection/10.1117/12.2569168.full](https://www.spiedigitallibrary.org/conference-proceedings-of-spie/11512/115121L/Contextual-copy-paste-data-augmentation-for-object-detection/10.1117/12.2569168.full)
*   **Description:** This paper explores a more advanced version of copy-paste by incorporating contextual information. It proposes training a classifier to determine suitable backgrounds for pasted objects, aiming to create more realistic and contextually coherent augmented images. This is in contrast to the "simple" method, which relies on random placement.

### 3. Revisiting Scalable Copy-Paste for Instance Segmentation using CLIP and StableDiffusion

*   **Link:** [https://mlr.press/r202-li/p21.html](https://mlr.press/r202-li/p21.html)
*   **Description:** This research modernizes the copy-paste technique by leveraging large-scale, zero-shot recognition models like CLIP and text-to-image models like Stable Diffusion. The proposed "X-Paste" method uses these models to generate a diverse and high-quality set of object instances to be pasted, making the copy-paste augmentation more scalable and effective, especially for long-tail distributions of objects.
