
import openai
from openai import OpenAI
import os
import base64
from io import BytesIO
from PIL import Image, ImageOps
import numpy as np
import re
import torch
from enum import Enum
import requests
from .mng_json import json_manager

#pip install pillow
#pip install bytesio

#Enum for style_prompt user input modes
class InputMode(Enum):
    IMAGE_PROMPT = 1
    IMAGE_ONLY = 2
    PROMPT_ONLY = 3


#Get information from the config.json file
class cFigSingleton:
    _instance = None

    def __new__(cls): 
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.get_file()
        return cls._instance
    
    
    def get_file(self):

        #Get script working directory
        j_mngr = json_manager()

        # Error handling is in the load_json method
        # Errors will be raised since is_critical is set to True
        config_data = j_mngr.load_json(j_mngr.config_file, True)

        #check if file is empty
        if not config_data:
            raise ValueError("Plush - Error: config.json contains no valid JSON data")
        
        #set property variables
        # Try getting API key from Plush environment variable
        self.figKey = os.getenv('OAI_KEY')
        # Try the openAI recommended Env Variable.
        if not self.figKey:
            self.figKey = os.getenv("OPENAI_API_KEY")
        # Temporary: Lastly get the API key from config.json
        if not self.figKey:
            self.figKey = config_data['key']
        # Final check to ensure an API key is set
        if not self.figKey:
            raise ValueError("Plush - Error: OpenAI API key not found. Please set it as an environment variable (See the Plush ReadMe).")
     
        self.figInstruction = config_data['instruction']
        self.figExample = config_data['example']
        self.figStyle = config_data['style']
        self.figImgInstruction = config_data['img_instruction']
        self.figImgPromptInstruction = config_data['img_prompt_instruction']
        try:
         self.figOAIClient = OpenAI(api_key= self.figKey)
        except Exception as e:
            print (f"Invalid OpenAI API key: {e}")
            raise

    @property
    def key(self)-> str:
        return self.figKey

    @property
    def instruction(self):
        return self.figInstruction
    
    @property
    def example(self):
        return self.figExample
    
    @property
    def style(self):
        #make sure the designated default value is present in the list
        if "Photograph" not in self.figStyle:
            self.figStyle.append("Photograph")

        return self.figStyle
    
    @property
    def ImgInstruction(self):
        return self.figImgInstruction
    
    @property
    def ImgPropmptInstruction(self):
        return self.figImgPromptInstruction
    
    @property
    def openaiClient(self)-> openai.OpenAI:
        return self.figOAIClient


class Enhancer:
#Build a creative prompt using a ChatGPT model    
   
    def __init__(self):
        self.cFig = cFigSingleton()

    def build_instruction(self, mode, style, elements, artist):
          #build the instruction from user input
        instruc = ""
        if mode == InputMode.PROMPT_ONLY:
            if self.cFig.instruction:
                instruc = self.cFig.instruction
            
        elif mode == InputMode.IMAGE_ONLY:
            if self.cFig.ImgInstruction:
                instruc = self.cFig.ImgInstruction
            
        elif mode == InputMode.IMAGE_PROMPT:
            if self.cFig.ImgPropmptInstruction:
                instruc = self.cFig.ImgPropmptInstruction

        if instruc.count("{}") >= 2:
            instruc = instruc.format(style, elements)
        elif instruc.count("{}") == 1:
            instruc = instruc.format(style)

        if artist >= 1:
            art_instruc = "  Include {} artist(s) who works in the specifed artistic style by placing the artists' name(s) at the end of the sentence prefaced by 'style of'."
            instruc += art_instruc.format(str(artist))

        return(instruc)
    
    def clean_response_text(self, text: str)-> str:
        # Replace multiple newlines or carriage returns with a single one
        cleaned_text = re.sub(r'\n+', '\n', text).strip()
        return cleaned_text

    def icgptRequest(self, GPTmodel, creative_latitude, tokens, prompt="", instruction="", example="", image=None,) :

        client = self.cFig.openaiClient
        # There's an image
        if image:
                
            GPTmodel = "gpt-4-vision-preview"  # Use vision model for image
            image_url = f"data:image/jpeg;base64,{image}"  # Assuming image is base64 encoded
           # messages.append({"role": "system", "content": {"type": "image_url", "image_url": {"url": image_url}}})

            headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cFig.key}" 
            }
            # messages list
            messages = []

            # Append the user message
            user_content = []
            if prompt:
                prompt = "PROMPT: " + prompt
                user_content.append({"type": "text", "text": prompt})

            user_content.append({"type": "image_url", "image_url": {"url": image_url}})
            messages.append({"role": "user", "content": user_content})

            # Append the system message if instruction is present
            if instruction:
                messages.append({"role": "system", "content": instruction})
            # Append the example in the assistant role
            if example:
                messages.append({"role": "assistant", "content": example})

            payload = {
            "model": GPTmodel,
            "max_tokens": tokens,
            "temperature": creative_latitude,
            "messages": messages
            }

            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response_json = response.json()
            CPTG_response = self.clean_response_text(response_json['choices'][0]['message']['content'] )

            return CPTG_response
        
        # No image
        messages = []

        if instruction:
            messages.append({"role": "system", "content": instruction})

        if prompt:
            messages.append({"role": "user", "content": prompt})
        else:
            # User has provided no prompt or image
            response = "empty box with 'NOTHING' printed on its side bold letters small flying moths dingy gloomy dim light rundown warehouse"
            return response
        if example:
            messages.append({"role": "assistant", "content": example})            
        

        try:
            response = client.chat.completions.create(
                model=GPTmodel,
                messages=messages,
                temperature=creative_latitude,
                max_tokens=tokens
            )

        except openai.APIConnectionError as e:
            print("Server connection error: {e.__cause__}")  # from httpx.
            raise
        except openai.RateLimitError as e:
            print(f"OpenAI RATE LIMIT error {e.status_code}: (e.response)")
            raise
        except openai.APIStatusError as e:
            print(f"OpenAI STATUS error {e.status_code}: (e.response)")
            raise
        except openai.BadRequestError as e:
            print(f"OpenAI BAD REQUEST error {e.status_code}: (e.response)")
            raise
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise   
        
        CPTG_response = response.choices[0].message.content
        return CPTG_response
        
    
    @classmethod
    def INPUT_TYPES(cls):
        iFig=cFigSingleton()

        #Floats have a problem, they go over the max value even when round and step are set, and the node fails.  So I set max a little over the expected input value
        return {
            "required": {
                "GPTmodel": (["gpt-3.5-turbo","gpt-4","gpt-4-1106-preview"],{"default": "gpt-4"} ),
                "creative_latitude" : ("FLOAT", {"max": 1.201, "min": 0.1, "step": 0.1, "display": "number", "round": 0.1, "default": 0.7}),                  
                "tokens" : ("INT", {"max": 8000, "min": 20, "step": 10, "default": 500, "display": "number"}),
                "example" : ("STRING", {"forceInput": True, "multiline": True}),
                "style": (iFig.style,{"default": "Photograph"}),
                "artist" : ("INT", {"max": 3, "min": 0, "step": 1, "default": 1, "display": "number"}),
                "max_elements" : ("INT", {"max": 25, "min": 3, "step": 1, "default": 10, "display": "number"}),
                "style_info" : ("BOOLEAN", {"default": False}),
                "prompt": ("STRING",{"multiline": True})                                
            },
            "optional": {            
                "image" : ("IMAGE", {"default": None})
            }
        } 

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("CGPTprompt", "CGPTinstruction","Style Info")

    FUNCTION = "gogo"

    OUTPUT_NODE = False

    CATEGORY = "Plush"
 

    def gogo(self, GPTmodel, creative_latitude, tokens, example, style, artist, max_elements, style_info, prompt, image=None):
        
        #If no example text was provided by the user, use my default
        if not example:
            example = self.cFig.example
            
        CGPT_styleInfo = None

        #Convert PyTorch.tensor to B64encoded image
        if isinstance(image, torch.Tensor):
            img_convert = DalleImage()
            image = img_convert.tensor_to_base64(image)

        #build instruction based on user input
        mode = 0
        if image and prompt:
            mode = InputMode.IMAGE_PROMPT
        elif image:
            mode = InputMode.IMAGE_ONLY
        elif prompt:
            mode = InputMode.PROMPT_ONLY

        instruction = self.build_instruction(mode, style, max_elements, artist)  

        if style_info:
            #User has request information about the art style.  GPT will provide it
            sty_prompt = "Give an 150 word backgrounder on the art style: {}.  Starting with describing what it is, include information about its history and which artists represent the style."
            sty_prompt = sty_prompt.format(style)
 
            CGPT_styleInfo = self.icgptRequest(GPTmodel, creative_latitude, tokens, sty_prompt )

        CGPT_prompt = self.icgptRequest(GPTmodel, creative_latitude, tokens, prompt, instruction, example, image)

    
        return (CGPT_prompt, instruction, CGPT_styleInfo)


class DalleImage:
#Accept a user prompt and parameters to produce a Dall_e generated image

    def __init__(self):
        self.cFig = cFigSingleton()

        
    def b64_to_tensor(self, b64_image: str) -> torch.Tensor:

        """
        Converts a base64-encoded image to a torch.Tensor.

        Note: ComfyUI expects the image tensor in the [N, H, W, C] format.  
        For example with the shape torch.Size([1, 1024, 1024, 3])

        Args:
            b64_image (str): The b64 image to convert.

        Returns:
            torch.Tensor: an image Tensor.
        """        
        # Decode the base64 string
        image_data = base64.b64decode(b64_image)
        
        # Open the image with PIL and handle EXIF orientation
        image = Image.open(BytesIO(image_data))
        image = ImageOps.exif_transpose(image)
        
        # Convert to RGB and normalize
        image = image.convert("RGB")
        image_np = np.array(image).astype(np.float32) / 255.0
        
        # Convert to PyTorch tensor
        tensor_image = torch.from_numpy(image_np)

        # Check shape and permute if necessary
        #if tensor_image.shape[-1] in [3, 4]:
            #tensor_image = tensor_image.permute(2, 0, 1)  # Convert to [C, H, W]  
  
        # Create a mask if there's an alpha channel
        if tensor_image.ndim == 3:  # If the tensor is [C, H, W]
            mask = torch.zeros_like(tensor_image[0, :, :], dtype=torch.float32)
        elif tensor_image.ndim == 4:  # If the tensor is [N, C, H, W]
            mask = torch.zeros_like(tensor_image[0, 0, :, :], dtype=torch.float32)

        if tensor_image.shape[1] == 4:  # Assuming channels are in the first dimension after unsqueeze
            mask = 1.0 - tensor_image[:, 3, :, :] / 255.0
        
        tensor_image = tensor_image.float()
        mask = mask.float()

        return tensor_image.unsqueeze(0), mask
    

    
    def tensor_to_base64(self, tensor: torch.Tensor) -> str:
        """
        Converts a PyTorch tensor to a base64-encoded image.

        Note: ComfyUI provides the image tensor in the [N, H, W, C] format.  
        For example with the shape torch.Size([1, 1024, 1024, 3])

        Args:
            tensor (torch.Tensor): The image tensor to convert.

        Returns:
            str: Base64-encoded image string.
        """
    # Convert tensor to PIL Image
        if tensor.ndim == 4:
            tensor = tensor.squeeze(0)  # Remove batch dimension if present
        pil_image = Image.fromarray((tensor.numpy() * 255).astype('uint8'))

        # Save PIL Image to a buffer
        buffer = BytesIO()
        pil_image.save(buffer, format="PNG")  # Can change to JPEG if preferred
        buffer.seek(0)

        # Encode buffer to base64
        base64_image = base64.b64encode(buffer.read()).decode('utf-8')

        return base64_image


    @classmethod
    def INPUT_TYPES(cls):
        #dall-e-2 API requires differnt input parameters as compared to dall-e-3, at this point I'll just use dall-e-3
        #                 "batch_size": ("INT", {"max": 8, "min": 1, "step": 1, "default": 1, "display": "number"})
        # Possible future implentation of batch_sizes greater than one.
        #                "image" : ("IMAGE", {"forceInput": True}),
        return {
            "required": {
                "GPTmodel": (["dall-e-3",], ),
                "prompt": ("STRING",{"multiline": True, "forceInput": True}), 
                "image_size": (["1792x1024", "1024x1792", "1024x1024"], {"default": "1024x1024"} ),              
                "image_quality": (["standard", "hd"], {"default": "hd"} ),
                "style": (["vivid", "natural"], {"default": "natural"} )
            },
        } 

    RETURN_TYPES = ("IMAGE", "MASK", "STRING" )
    RETURN_NAMES = ("image", "mask", "Dall_e_prompt")

    FUNCTION = "gogo"

    OUTPUT_NODE = False

    CATEGORY = "Plush"

    def gogo(self, GPTmodel, prompt, image_size, image_quality, style):
                
        client = self.cFig.openaiClient
        
        print(f"Talking to Dalle model: {GPTmodel}")
        try:
            response = client.images.generate(
                model = GPTmodel,
                prompt = prompt, 
                size = image_size,
                quality = image_quality,
                style = style,
                n=1,
                response_format = "b64_json",
            )
        except openai.APIConnectionError as e:
            print("Server connection error: {e.__cause__}")  # from httpx.
            raise
        except openai.RateLimitError as e:
            print(f"OpenAI RATE LIMIT error {e.status_code}: (e.response)")
            raise
        except openai.APIStatusError as e:
            print(f"OpenAI STATUS error {e.status_code}: (e.response)")
            raise
        except openai.BadRequestError as e:
            print(f"OpenAI BAD REQUEST error {e.status_code}: (e.response)")
            raise
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise

 
      # Get the revised_prompt
        revised_prompt = response.data[0].revised_prompt

        #Convert the b64 json to a pytorch tensor

        b64Json = response.data[0].b64_json

        png_image, mask = self.b64_to_tensor(b64Json)        
        
        return (png_image, mask.unsqueeze(0), revised_prompt)
    

# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {
    "Enhancer": Enhancer,
    "DalleImage": DalleImage
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "Enhancer": "Style Prompt",
    "DalleImage": "OAI Dall_e Image"
}
    


#debug testing  DalleImage
""" Di = DalleImage()
ddict = Di.INPUT_TYPES()
tst = []
tst = Di.gogo("dall-e-3", "A woman standing by a flowing river", "1024x1024", "hd", "natural")
myname = tst[0].names  """

#debug testing Enhancer
#**********Load and convert test image file*************    
""" img_convert = DalleImage()
j_mngr = json_manager()
image_path = os.path.join(j_mngr.script_dir, 'test_img.png')
with open(image_path, "rb") as image_file:
    image_file = base64.b64encode(image_file.read()).decode('utf-8')
tensor_image, mask = img_convert.b64_to_tensor(image_file)
tensor_image = None 
#*************End Image File****************************
#image_file = None

Enh = Enhancer()
Enh.INPUT_TYPES()
test_resp = Enh.gogo("gpt-4", 0.7, 2000, "", None, "Shallow Depth of Field Photograph", 2, 10,False, tensor_image)
print (test_resp[0])"""