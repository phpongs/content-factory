import os
import requests
import time

API_URL = "http://127.0.0.1:8080/api/v1/videos"

topics = [
    {
        "subject": "Antifragility",
        "script": "Stop scrolling! Did you know that being resilient is actually not enough to succeed in today's chaotic world? There is a massive difference between resilience and antifragility. When a resilient person faces a crisis, they just survive and return to their original baseline. But an antifragile person? They actually grow stronger from the chaos! Think about your muscles. When you lift heavy weights, you put them under intense stress. They don't just bounce back to normal; they rebuild themselves to be significantly stronger and larger than before. That is antifragility in action. In your career, finances, and personal life, you shouldn't just seek safety. You should actively build systems that benefit from shocks and unpredictability. Start seeing every failure, every rejection, and every unexpected problem as the exact fuel you need to level up. Embrace the chaos, adapt rapidly, and let the difficult times forge you into something unbreakable. Hit follow for more life-changing secrets!",
        "terms": ["resilience", "strong muscle", "chaos", "success", "adaptation"]
    },
    {
        "subject": "Attention Economy",
        "script": "If you feel exhausted at the end of every day but haven't actually accomplished anything, you are a victim of the attention economy. Right now, your attention is the most valuable commodity on the planet. Trillions of dollars are spent by tech companies to design algorithms, notifications, and endless feeds specifically engineered to hijack your focus. Every time you casually open an app just to check a quick message, you are voluntarily handing over your most precious asset. Wealthy and successful people protect their attention ruthlessly. They understand that where your focus goes, your energy flows, and eventually, your reality is shaped. If you want to take back control of your life, you need to start treating your attention like a billionaire treats their bank account. Turn off non-essential notifications, set strict boundaries around your screen time, and guard your deep work hours like your life depends on it. Hit follow for more life-changing secrets!",
        "terms": ["social media addict", "billionaire", "focus", "deep work", "smartphone"]
    },
    {
        "subject": "Blue Ocean Strategy",
        "script": "Why are you still competing in a bloody red ocean when you could create your own blue ocean? Most entrepreneurs and creators make the exact same mistake. They look at what everyone else is doing and try to do it just a tiny bit better or a little bit cheaper. This leads to vicious competition, shrinking profit margins, and inevitable burnout. Instead, you need to study the Blue Ocean Strategy. Stop fighting over the exact same customers. Look for entirely new markets where the competition is literally irrelevant. Think about Cirque du Soleil. They didn't try to compete with traditional circuses by hiring more clowns or cheaper animals. They completely reinvented the industry by combining circus arts with sophisticated theater, targeting adults who were willing to pay premium ticket prices. To succeed, you must innovate your value proposition. Stop copying the crowd. Redefine the rules of the game so you are the only player. Hit follow for more life-changing secrets!",
        "terms": ["ocean", "business meeting", "circus", "innovation", "success"]
    },
    {
        "subject": "Cognitive Overload",
        "script": "Your brain is literally drowning right now, and it is destroying your potential. We consume more information in a single day than our ancestors consumed in an entire lifetime. This constant barrage of emails, texts, podcasts, and endless scrolling creates massive cognitive overload. When your working memory is completely maxed out, your brain loses its ability to think deeply, solve complex problems, or even regulate your emotions properly. This is why you feel constantly anxious and unable to focus on the tasks that actually matter. The solution is not better time management; it is aggressive information fasting. You need to intentionally create periods of profound boredom in your day. Go for a long walk without your phone. Sit in a quiet room and just let your mind wander. By intentionally reducing the inputs, you allow your brain to finally process, connect ideas, and achieve the deep clarity required for real success. Hit follow for more life-changing secrets!",
        "terms": ["brain overload", "walking alone", "meditation", "stress", "clarity"]
    },
    {
        "subject": "Comfort Zone Trap",
        "script": "Your comfort zone is the most dangerous place on earth. It feels incredibly safe, warm, and secure, but in reality, it is a silent killer of all your potential. Every single significant breakthrough in your life, your career, your relationships, and your finances exists entirely outside of what is comfortable. When you constantly choose the easy path, you signal to your brain that growth is no longer necessary. Over time, your skills stagnate, your confidence slowly erodes, and you become terrified of even the smallest risks. If you want to achieve extraordinary results, you have to intentionally schedule discomfort into your daily routine. Have that difficult conversation you've been avoiding. Start that ambitious project even if you feel completely unqualified. Go to the gym when you are tired. The moment you start feeling uncomfortable is the exact moment you start actually growing. Stop settling for an average life. Step out of the zone. Hit follow for more life-changing secrets!",
        "terms": ["comfort zone", "gym workout", "business success", "taking risk", "growth"]
    }
]

def submit_task(topic_data, bgm_index):
    payload = {
        "video_subject": f"Vault: {topic_data['subject']}",
        "video_aspect": "9:16",
        "video_language": "en-US",
        "voice_name": "en-US-AndrewMultilingualNeural-V2-Male", # Keep using the high-quality Azure voice
        "bgm_type": "custom",
        "bgm_file": f"output02{bgm_index}.mp3", # Rotate BGMs
        "subtitle_enabled": True,
        "video_script": topic_data['script'],
        "video_terms": topic_data['terms']
    }

    print(f"Submitting task: {topic_data['subject']}...")
    try:
        response = requests.post(API_URL, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        print(f"  -> Success! Task ID: {result.get('data', {}).get('task_id')}")
    except requests.exceptions.RequestException as e:
        print(f"  -> Error submitting task: {e}")

if __name__ == "__main__":
    print("Batch generating 5 videos from Vault concepts...")
    for i, topic in enumerate(topics):
        # Rotate BGM files from output020.mp3 to output024.mp3
        bgm_idx = i % 5
        submit_task(topic, bgm_idx)
        time.sleep(2) # Brief pause between requests

    print("\nAll 5 tasks have been submitted to MoneyPrinterTurbo!")
