import { patch } from "@web/core/utils/patch";
import { CategorySelector } from "@point_of_sale/app/components/category_selector/category_selector";

patch(CategorySelector.prototype, {
    getChildCategoriesInfo(category) {
        const info = super.getChildCategoriesInfo(category);
        const hasEmoji = category.pos_category_icon && category.pos_category_icon !== "none";
        const hasCustomImg = !!category.pos_category_icon_image;
        return {
            ...info,
            gyIcon: hasEmoji
                ? category.pos_category_icon
                : hasCustomImg
                    ? `/web/image?model=pos.category&field=pos_category_icon_image&id=${category.id}`
                    : null,
            gyIconIsImage: !hasEmoji && hasCustomImg,
            // Penanda chip AKTIF untuk tema (dipakai `gy-category--active` di
            // category_selector_patch.xml).
            //
            // Kenapa tidak memakai `info.isSelected` yang sudah ada: di Odoo 19
            // isSelected = [undefined, ...allParents, selected].includes(category),
            // jadi LELUHUR dari kategori terpilih ikut bernilai true. Hasil ukur
            // 19 Sep 2026: keenam chip tampil "aktif" sekaligus. Yang boleh
            // berwarna merah hanya kategori yang
            // benar-benar dipilih, jadi pembandingnya harus `selectedCategory.id`.
            gyIsActive: category.id === this.pos.selectedCategory?.id,
        };
    },
});
