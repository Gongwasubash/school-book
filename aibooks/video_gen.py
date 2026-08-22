import os
import uuid
from typing import List, Dict, Any

class VideoGenerator:
    """Generates NotebookLM-style educational videos from textbook chapters."""
    
    def __init__(self, video_dir: str = "video_outputs"):
        self.video_dir = video_dir
        os.makedirs(video_dir, exist_ok=True)
        
    def generate_video_script(self, chapter_title: str, content: str) -> Dict[str, Any]:
        """Generate a video script with narration and slide structure."""
        script = {
            "title": f"Learning Module: {chapter_title}",
            "sections": [],
            "audio_script": "",
            "slides": []
        }
        
        # Analyze content to create structured sections
        sections = self._analyze_content(content)
        
        for i, section in enumerate(sections):
            slide = {
                "title": f"Section {i+1}: {section['title']}",
                "content": section['content'],
                "key_points": section['points'],
                "visuals": section['visuals']
            }
            script["sections"].append(slide)
            script["audio_script"] += f"Section {i+1}: {section['title']} - {section['content']} "
        
        # Generate audio script
        script["audio_script"] = self._generate_audio_script(script)
        
        return script
    
    def _analyze_content(self, content: str) -> List[Dict]:
        """Analyze content to identify logical sections."""
        sections = []
        lines = content.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith(('## ', '## ')) or line.isupper() or len(line) < 20:
                # Section header
                section_title = line.lstrip('# ').strip()
                sections.append({
                    "title": section_title,
                    "content": "",
                    "points": [],
                    "visuals": []
                })
                current_section = section_title
            elif current_section:
                # Add content to current section
                if current_section in [s['title'] for s in sections]:
                    current_section_obj = next(s for s in sections if s['title'] == current_section)
                    current_section_obj['content'] += f" {line}"
                    current_section_obj['points'].append(line)
        
        return sections
    
    def _generate_audio_script(self, script: Dict) -> str:
        """Generate a narrated script for the video."""
        audio_script = "Welcome to this educational video module.\n\n"
        for i, section in enumerate(script["sections"]):
            audio_script += f"\n[Slide {i+1}: {section['title']}]\n"
            audio_script += f"{section['content']}\n"
            audio_script += f"Key points: {', '.join(section['points'])}\n"
        return audio_script

def generate_video_script(chapter_title: str, content: str, output_dir: str = "video_outputs"):
    """Main function to generate a video script."""
    generator = VideoGenerator(video_dir=video_dir)
    return generator.generate_video_script(chapter_title, content)