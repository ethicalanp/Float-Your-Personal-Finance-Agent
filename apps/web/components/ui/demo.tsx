import { Phone } from "lucide-react";
import { SocialButton } from "@/components/ui/social-button";

export default function SocialButtonIconOnlyDemo() {
  return (
    <div className="flex gap-3">
      <SocialButton brand="google" appearance="white" iconOnly />

      <SocialButton brand="apple" appearance="white" iconOnly />

      <SocialButton
        brand="custom"
        appearance="white"
        iconOnly
        config={{
          label: "Phone",
          icon: <Phone className="size-4" />,
          color: "#000000",
        }}
      />
    </div>
  );
}
